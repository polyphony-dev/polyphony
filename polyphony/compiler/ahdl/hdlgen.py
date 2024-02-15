
from .ahdl import *
from .transformers.varcollector import AHDLVarCollector
from .transformers.varreplacer import AHDLSignalReplacer
from .hdlmodule import HDLModule
from ..common.env import env
from ..ir.ir import *
from ..ir.irhelper import qualified_symbols
from logging import getLogger
logger = getLogger(__name__)


class HDLModuleBuilder(object):
    @classmethod
    def create(cls, hdlmodule):
        if hdlmodule.scope.is_module():
            return HDLTopModuleBuilder()
        elif hdlmodule.scope.is_testbench():
            return HDLTestbenchBuilder()
        elif hdlmodule.scope.is_function_module():
            return HDLFunctionModuleBuilder()
        else:
            assert False

    def process(self, hdlmodule:HDLModule):
        self.hdlmodule:HDLModule = hdlmodule
        self._collector = AHDLVarCollector()
        self._build_module()

    def _build_module(self):
        pass

    def _process_submodules(self):
        subscopes = set()
        self._collector.process(self.hdlmodule)
        for vars in self._collector.submodule_vars():
            subscopes.add((vars[0], self.hdlmodule.subscopes[vars[0]]))
        for instance_sig, subscope in subscopes:
            param_map = {}
            if subscope.scope.module_param_vars:
                for name, v in subscope.scope.module_param_vars:
                    param_map[name] = v
            connections = []
            for (var, connector_name, attrs) in subscope.connectors(instance_sig.name):
                connector = self.hdlmodule.gen_sig(connector_name, var.sig.width, attrs)
                connections.append((var, connector))
            self.hdlmodule.add_sub_module(instance_sig.name,
                                          subscope,
                                          connections,
                                          param_map=param_map)
            # replace port access to connector
            replace_table:dict[tuple, tuple] = {}
            for var, connector in connections:
                vars = (instance_sig,) + var.vars
                replace_table[vars] = (connector,)
            AHDLSignalReplacer(replace_table).process(self.hdlmodule)
            logger.debug(str(self.hdlmodule))

    def _add_callee_submodules(self, scope):
        for callee_scope, inst_names in scope.callee_instances.items():
            if callee_scope.is_port():
                continue
            if callee_scope.is_lib():
                continue
            inst_scope_name = callee_scope.base_name
            # TODO: add primitive function hook here
            if inst_scope_name == 'print':
                continue
            self._add_submodule_instances(env.hdlscope(callee_scope), inst_names, {})

    def _add_submodule_instances(self, sub_hdlmodule, inst_names, param_map, is_internal=False):
        for inst_name in inst_names:
            connections = []
            for (var, connector_name, attrs) in sub_hdlmodule.connectors(inst_name):
                connector = self.hdlmodule.gen_sig(connector_name, var.sig.width, attrs)
                connections.append((var, connector))
            self.hdlmodule.add_sub_module(inst_name,
                                          sub_hdlmodule,
                                          connections,
                                          param_map=param_map)

    def _add_roms(self, memvars_set:set[tuple[Signal]]):
        def find_defstm(symbol):
            defstms = symbol.scope.usedef.get_stms_defining(symbol)
            if defstms:
                assert len(defstms) == 1
                return list(defstms)[0]
            defstms = symbol.scope.field_usedef.get_def_stms((symbol,))
            assert len(defstms) == 1
            return list(defstms)[0]

        roms = [memvars for memvars in memvars_set if memvars[-1].is_rom()]
        while roms:
            memvars = roms.pop()
            fname = AHDL_VAR(memvars, Ctx.STORE)
            addr_width = 8  # TODO
            input_sig = self.hdlmodule.gen_sig(memvars[-1].name + '_in', addr_width)
            input = AHDL_VAR(input_sig, Ctx.LOAD)

            array_sym = memvars[-1].sym
            while True:
                defstm = find_defstm(array_sym)
                array = defstm.src
                if array.is_a(ARRAY):
                    break
                elif array.is_a(IRVariable):
                    array_sym = qualified_symbols(array, array_sym.scope)[-1]
                    # array_sym = array.symbol
                else:
                    assert False
            case_items = []
            assert array.repeat.is_a(CONST)
            items = array.items * array.repeat.value
            for i, item in enumerate(items):
                assert item.is_a(CONST)
                connect = AHDL_BLOCK(str(i), (AHDL_CONNECT(fname, AHDL_CONST(item.value)), ))
                case_items.append(AHDL_CASE_ITEM(AHDL_CONST(i), connect))
            case = AHDL_CASE(input, tuple(case_items))
            rom_func = AHDL_FUNCTION(fname, (input,), (case,))
            self.hdlmodule.add_function(rom_func)

    def _collect_moves(self, fsm):
        moves = []
        for stg in fsm.stgs:
            for state in stg.states:
                moves.extend([code for code in state.traverse() if code.is_a(AHDL_MOVE)])
        return moves

    def _add_reset_stms(self, fsm, defs:set[tuple[Signal]], uses:set[tuple[Signal]], outputs:set[tuple[Signal]]):
        fsm_name = fsm.name
        for vars in defs | outputs:
            if vars[0].is_dut():
                continue
            if vars[-1].is_reg():
                if vars[-1].is_initializable():
                    v = AHDL_CONST(vars[-1].init_value)
                else:
                    v = AHDL_CONST(0)
                mv = AHDL_MOVE(AHDL_VAR(vars, Ctx.STORE), v)
                self.hdlmodule.add_fsm_reset_stm(fsm_name, mv)


class HDLFunctionModuleBuilder(HDLModuleBuilder):
    def _build_module(self):
        assert len(self.hdlmodule.fsms) == 1
        fsm = self.hdlmodule.fsms[self.hdlmodule.name]
        scope = fsm.scope
        self._add_input(scope)
        self._add_output(scope)
        self._add_callee_submodules(scope)
        self._collector.process(self.hdlmodule)
        self._add_roms(self._collector.mem_vars(fsm.name))
        self._add_reset_stms(fsm,
                             self._collector.def_vars(fsm.name),
                             self._collector.use_vars(fsm.name),
                             self._collector.output_vars(fsm.name))

    def _add_input(self, scope):
        if scope.is_method():
            assert False
        for sym in scope.param_symbols():
            if sym.typ.is_int() or sym.typ.is_bool():
                sig = self.hdlmodule.signal(sym)
            elif sym.typ.is_seq():
                raise NotImplementedError()
            else:
                assert False
            assert sig
            self.hdlmodule.add_input(AHDL_VAR(sig, Ctx.LOAD))
        module_name = self.hdlmodule.name
        sig = self.hdlmodule.gen_sig(f'{module_name}_ready', 1, {'input', 'net', 'ctrl'})
        self.hdlmodule.add_input(AHDL_VAR(sig, Ctx.LOAD))
        sig = self.hdlmodule.gen_sig(f'{module_name}_accept', 1, {'input', 'net', 'ctrl'})
        self.hdlmodule.add_input(AHDL_VAR(sig, Ctx.LOAD))

    def _add_output(self, scope):
        if scope.return_type.is_scalar():
            sig_name = '{}_out_0'.format(scope.base_name)
            sig = self.hdlmodule.signal(sig_name)
            assert sig
            self.hdlmodule.add_output(AHDL_VAR(sig, Ctx.STORE))
        elif scope.return_type.is_seq():
            raise NotImplementedError('return of a suquence type is not implemented')
        module_name = self.hdlmodule.name
        sig = self.hdlmodule.gen_sig(f'{module_name}_valid', 1, {'output', 'reg', 'ctrl'})
        self.hdlmodule.add_output(AHDL_VAR(sig, Ctx.STORE))


class HDLTestbenchBuilder(HDLModuleBuilder):
    def _build_module(self):
        assert len(self.hdlmodule.fsms) == 1
        fsm = self.hdlmodule.fsms[self.hdlmodule.name]
        scope = fsm.scope
        self._add_callee_submodules(scope)

        self._process_submodules()
        self._collector.process(self.hdlmodule)
        self._add_roms(self._collector.mem_vars(fsm.name))
        self._add_reset_stms(fsm,
                             self._collector.def_vars(fsm.name),
                             self._collector.use_vars(fsm.name),
                             self._collector.output_vars(fsm.name))



class HDLTopModuleBuilder(HDLModuleBuilder):
    def _process_io(self, hdlmodule):
        def collect_io(topmodule, hdlmodule, prefix_qsig):
            for sig in hdlmodule.get_signals({'single_port'}, exclude_tags=None, with_base=True):
                if sig.is_input():
                    topmodule.add_input(AHDL_VAR(prefix_qsig + (sig,), Ctx.LOAD))
                elif sig.is_output():
                    topmodule.add_output(AHDL_VAR(prefix_qsig + (sig,), Ctx.LOAD))
            for sig in hdlmodule.get_signals({'subscope'}, exclude_tags=None):
                subscope = hdlmodule.subscopes[sig]
                collect_io(topmodule, subscope, prefix_qsig + (sig,))

        collect_io(self.hdlmodule, self.hdlmodule, tuple())

    def _process_fsm(self, fsm):
        scope = fsm.scope
        self._add_callee_submodules(scope)
        self._add_roms(self._collector.mem_vars(fsm.name))
        self._add_reset_stms(fsm,
                             self._collector.def_vars(fsm.name),
                             self._collector.use_vars(fsm.name),
                             self._collector.output_vars(fsm.name))

    def _build_module(self):
        assert self.hdlmodule.scope.is_module()
        assert self.hdlmodule.scope.is_class()
        if not self.hdlmodule.scope.is_instantiated():
            return
        for p in self.hdlmodule.scope.module_params:
            sig = self.hdlmodule.signal(p.copy)
            assert sig
            val = 0 if not p.defval else p.defval.value
            self.hdlmodule.parameters.append((sig, val))
        self._process_io(self.hdlmodule)

        self._collector.process(self.hdlmodule)
        fsms = list(self.hdlmodule.fsms.values())
        for fsm in fsms:
            if fsm.scope.is_ctor():
                self._add_roms(self._collector.mem_vars(fsm.name))
                # remove ctor fsm and add constant parameter assigns
                for stm in self._collect_module_defs(fsm):
                    if stm.dst.sig.is_field():
                        if stm.dst.sig.is_net():
                            assign = AHDL_ASSIGN(stm.dst, stm.src)
                            self.hdlmodule.add_static_assignment(assign, '')
                del self.hdlmodule.fsms[fsm.name]
            else:
                self._process_fsm(fsm)

    def _collect_module_defs(self, fsm):
        moves = self._collect_moves(fsm)
        defs = []
        for mv in moves:
            if (mv.dst.is_a(AHDL_VAR) and
                    (mv.dst.sig.is_output() or
                     mv.dst.sig.is_field())):
                defs.append(mv)
        return defs


