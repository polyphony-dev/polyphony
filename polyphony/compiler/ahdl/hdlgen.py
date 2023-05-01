from collections import defaultdict
from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from ..common.env import env
from ..ir.ir import *
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

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        self._build_module()

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
            ios = sub_hdlmodule.inputs() + sub_hdlmodule.outputs()
            for sig in ios:
                if sub_hdlmodule.scope.is_module():
                    ifname = sig.name
                else:
                    ifname = sig.name[len(sub_hdlmodule.name) + 1:]
                accessor_name = f'{inst_name}_{ifname}'
                attr = {'extport'}
                if sig.is_input():
                    attr.add('reg')
                else:
                    attr.add('net')
                if sig.is_ctrl():
                    attr.add('ctrl')
                accessor = self.hdlmodule.gen_sig(accessor_name, sig.width, attr)
                connections.append((sig, accessor))
            self.hdlmodule.add_sub_module(inst_name,
                                          sub_hdlmodule,
                                          connections,
                                          param_map=param_map)

    def _add_roms(self, memsigs):
        def find_defstm(symbol):
            # use ancestor if it is imported symbol
            if symbol.scope.is_containable() and symbol.is_imported():
                symbol = symbol.import_src()
            defstms = symbol.scope.usedef.get_stms_defining(symbol)
            if defstms:
                assert len(defstms) == 1
                return list(defstms)[0]
            defstms = symbol.scope.field_usedef.get_stms_defining(symbol)
            assert len(defstms) == 1
            return list(defstms)[0]

        roms = [sig for sig in memsigs if sig.is_rom()]
        while roms:
            output_sig = roms.pop()
            fname = AHDL_VAR(output_sig, Ctx.STORE)
            addr_width = 8  # TODO
            input_sig = self.hdlmodule.gen_sig(output_sig.name + '_in', addr_width)
            input = AHDL_VAR(input_sig, Ctx.LOAD)

            array_sym = output_sig.sym
            while True:
                defstm = find_defstm(array_sym)
                array = defstm.src
                if array.is_a(ARRAY):
                    break
                elif array.is_a([TEMP, ATTR]):
                    array_sym = array.symbol
                else:
                    assert False
            case_items = []
            for i, item in enumerate(array.items):
                assert item.is_a(CONST)
                connect = AHDL_BLOCK(str(i), (AHDL_CONNECT(fname, AHDL_CONST(item.value)), ))
                case_items.append(AHDL_CASE_ITEM(AHDL_CONST(i), connect))
            case = AHDL_CASE(input, tuple(case_items))
            rom_func = AHDL_FUNCTION(fname, (input,), (case,))
            self.hdlmodule.add_function(rom_func)

    def _collect_vars(self, fsm):
        outputs = set()
        defs = set()
        uses = set()
        memnodes = set()
        collector = AHDLVarCollector(self.hdlmodule, defs, uses, outputs, memnodes)
        for stg in fsm.stgs:
            for state in stg.states:
                collector.visit(state)
        return defs, uses, outputs, memnodes

    def _collect_moves(self, fsm):
        moves = []
        for stg in fsm.stgs:
            for state in stg.states:
                moves.extend([code for code in state.traverse() if code.is_a(AHDL_MOVE)])
        return moves

    def _add_reset_stms(self, fsm, defs, uses, outputs):
        fsm_name = fsm.name
        for sig in defs | outputs:
            if sig.is_reg():
                if sig.is_initializable():
                    v = AHDL_CONST(sig.init_value)
                else:
                    v = AHDL_CONST(0)
                mv = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), v)
                self.hdlmodule.add_fsm_reset_stm(fsm_name, mv)


class HDLFunctionModuleBuilder(HDLModuleBuilder):
    def _build_module(self):
        assert len(self.hdlmodule.fsms) == 1
        fsm = self.hdlmodule.fsms[self.hdlmodule.name]
        scope = fsm.scope
        defs, uses, outputs, memnodes = self._collect_vars(fsm)
        self._add_input(scope)
        self._add_output(scope)
        self._add_callee_submodules(scope)
        self._add_roms(memnodes)
        self._add_reset_stms(fsm, defs, uses, outputs)

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
            self.hdlmodule.add_input(sig)
        module_name = self.hdlmodule.name
        sig = self.hdlmodule.gen_sig(f'{module_name}_ready', 1, {'input', 'net', 'ctrl'})
        self.hdlmodule.add_input(sig)
        sig = self.hdlmodule.gen_sig(f'{module_name}_accept', 1, {'input', 'net', 'ctrl'})
        self.hdlmodule.add_input(sig)

    def _add_output(self, scope):
        if scope.return_type.is_scalar():
            sig_name = '{}_out_0'.format(scope.base_name)
            sig = self.hdlmodule.signal(sig_name)
            self.hdlmodule.add_output(sig)
        elif scope.return_type.is_seq():
            raise NotImplementedError('return of a suquence type is not implemented')
        module_name = self.hdlmodule.name
        sig = self.hdlmodule.gen_sig(f'{module_name}_valid', 1, {'output', 'reg', 'ctrl'})
        self.hdlmodule.add_output(sig)


class HDLTestbenchBuilder(HDLModuleBuilder):
    def _build_module(self):
        assert len(self.hdlmodule.fsms) == 1
        fsm = self.hdlmodule.fsms[self.hdlmodule.name]
        scope = fsm.scope
        defs, uses, outputs, memnodes = self._collect_vars(fsm)
        self._add_callee_submodules(scope)
        for p_name, p_typ in zip(scope.param_names(), scope.param_types()):
            if p_typ.is_object() and p_typ.scope.is_module():
                mod_scope = p_typ.scope
                sub_hdlmodule = env.hdlscope(mod_scope)
                param_map = {}
                if sub_hdlmodule.scope.module_param_vars:
                    for name, v in sub_hdlmodule.scope.module_param_vars:
                        param_map[name] = v
                self._add_submodule_instances(sub_hdlmodule, [p_name], param_map=param_map)
        self._add_roms(memnodes)
        self._add_reset_stms(fsm, defs, uses, outputs)


class HDLTopModuleBuilder(HDLModuleBuilder):
    def _process_io(self, hdlmodule):
        for sig in hdlmodule.get_signals({'single_port'}, None, with_base=True):
            if sig.is_input():
                hdlmodule.add_input(sig)
            elif sig.is_output():
                hdlmodule.add_output(sig)

    def _process_fsm(self, fsm):
        scope = fsm.scope
        defs, uses, outputs, memnodes = self._collect_vars(fsm)
        self._add_callee_submodules(scope)
        self._add_roms(memnodes)
        self._add_reset_stms(fsm, defs, uses, outputs)

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

        fsms = list(self.hdlmodule.fsms.values())
        for fsm in fsms:
            if fsm.scope.is_ctor():
                memsigs = self.hdlmodule.get_signals({'regarray', 'netarray'})
                self._add_roms(memsigs)

                #for memnode in env.memref_graph.collect_ram(self.hdlmodule.scope):
                for sym in self.hdlmodule.scope.symbols.values():
                    if not sym.typ.is_list() or sym.typ.ro:
                        continue
                    name = sym.hdl_name()
                    width = sym.typ.element.width
                    length = sym.typ.length
                    sig = self.hdlmodule.gen_sig(name, (width, length), {'regarray'})
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


class AHDLVarCollector(AHDLVisitor):
    '''this class collects inputs and outputs and locals'''
    def __init__(self, hdlmodule, local_defs, local_uses, output_temps, mems):
        self.local_defs = local_defs
        self.local_uses = local_uses
        self.output_temps = output_temps
        self.module_constants = [c for c, _ in hdlmodule.constants.keys()]
        self.mems = mems

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.ctx & Ctx.STORE:
            self.local_defs.add(ahdl.sig)
        else:
            self.local_uses.add(ahdl.sig)
        self.mems.add(ahdl.sig)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig.is_ctrl() or ahdl.sig in self.module_constants:
            pass
        elif ahdl.sig.is_input():
            if ahdl.sig.is_single_port():
                self.output_temps.add(ahdl.sig)
        elif ahdl.sig.is_output():
            self.output_temps.add(ahdl.sig)
        else:
            if ahdl.ctx & Ctx.STORE:
                self.local_defs.add(ahdl.sig)
            else:
                self.local_uses.add(ahdl.sig)
