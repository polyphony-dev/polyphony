
from .ahdl import *
from .transformers.varcollector import AHDLVarCollector
from .transformers.varreplacer import AHDLSignalReplacer
from .hdlmodule import HDLModule
from ..common.env import env
from ..ir.ir import *
from ..ir.irhelper import qualified_symbols
from ..ir.analysis.usedef import UseDefDetector
from ..ir.analysis.fieldusedef import FieldUseDef
from logging import getLogger
logger = getLogger(__name__)


class HDLModuleBuilder(object):
    @classmethod
    def create(cls, hdlmodule):
        if hdlmodule.scope.is_module():
            if env.config.flatten_modules:
                return HDLTopModuleBuilderFlatten()
            else:
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
        for instance_sig, subscope in self.hdlmodule.subscopes.items():
            if not isinstance(subscope, HDLModule):
                # Skip non-module subscopes (e.g., plain-class objects)
                continue
            param_map = {}
            cls = subscope.scope.as_class()
            if cls and cls.module_param_vars:
                for name, v in cls.module_param_vars:
                    param_map[name] = v
            connections = []
            for (var, connector_name, attrs) in cast(HDLModule, subscope).connectors(instance_sig.name):
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

    def _add_roms(self, memvars_set:set[tuple[Signal]]):
        def find_defstm(symbol):
            usedef = UseDefDetector().process(symbol.scope)
            defstms = usedef.get_stms_defining(symbol)
            if defstms:
                assert len(defstms) == 1
                return list(defstms)[0]
            module_scope = symbol.scope
            while module_scope is not None and not module_scope.is_module():
                module_scope = module_scope.parent
            field_usedef = FieldUseDef().process(module_scope)
            defstms = field_usedef.get_def_stms((symbol,))
            assert len(defstms) == 1
            return list(defstms)[0]

        roms = sorted([memvars for memvars in memvars_set if memvars[-1].is_rom()], key=lambda mv: mv[-1].name)
        for memvars in roms:
            fname = AHDL_VAR(memvars, Ctx.STORE)
            addr_width = 8  # TODO
            input_sig = self.hdlmodule.gen_sig(f'{fname.hdl_name}_in', addr_width)
            input = AHDL_VAR(input_sig, Ctx.LOAD)

            array_sym = memvars[-1].sym
            while True:
                defstm = find_defstm(array_sym)
                array = defstm.src
                if isinstance(array, Array):
                    break
                elif isinstance(array, IrVariable):
                    array_sym = qualified_symbols(array, array_sym.scope)[-1]
                else:
                    assert False
            case_items = []
            assert isinstance(array.repeat, Const)
            items = array.items * array.repeat.value
            for i, item in enumerate(items):
                assert isinstance(item, Const)
                connect = AHDL_BLOCK(str(i), (AHDL_CONNECT(fname, AHDL_CONST(item.value)), ))
                case_items.append(AHDL_CASE_ITEM(AHDL_CONST(i), connect))
            case = AHDL_CASE(input, tuple(case_items))
            rom_func = AHDL_FUNCTION(fname, (input,), (case,))
            self.hdlmodule.add_function(rom_func)

    def _collect_moves(self, fsm):
        moves = []
        for stg in fsm.stgs:
            for state in stg.states:
                moves.extend([code for code in state.traverse() if isinstance(code, AHDL_MOVE)])
        return moves

    def _add_reset_stms(self, fsm, defs:set[tuple[Signal]], uses:set[tuple[Signal]], outputs:set[tuple[Signal]]):
        fsm_name = fsm.name
        # Use only defs (signals written by this FSM) to avoid multi-driver resets
        # when multiple FSMs reference the same output signal.
        for vars in sorted(defs, key=lambda v: v[-1].name):
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
        self._process_submodules()
        self._collector.process(self.hdlmodule)
        self._add_roms(self._collector.mem_vars(fsm.name))
        self._add_reset_stms(fsm,
                             self._collector.def_vars(fsm.name),
                             self._collector.use_vars(fsm.name),
                             self._collector.output_vars(fsm.name))



class HDLTopModuleBuilder(HDLModuleBuilder):
    """Builder for module scopes in individual compilation mode."""

    def _process_io(self, hdlmodule):
        for sig in hdlmodule.get_signals({'single_port'}, exclude_tags=None, with_base=True):
            if sig.is_input():
                hdlmodule.add_input(AHDL_VAR((sig,), Ctx.LOAD))
            elif sig.is_output():
                hdlmodule.add_output(AHDL_VAR((sig,), Ctx.LOAD))
        # Determine whether submodule connectors should be I/O ports:
        # - If parent has workers, they drive submodule ports internally
        #   → connectors are internal wires (not I/O)
        # - If parent has no workers, testbench accesses submodule ports
        #   via parent I/O → connectors become I/O ports
        has_workers = len(self.hdlmodule.scope.workers) > 0
        for _, _, connections, _ in self.hdlmodule.sub_modules.values():
            for sub_var, connector in connections:
                connector.width = sub_var.sig.width
                if sub_var.sig.is_int():
                    connector.add_tag('int')
                if has_workers:
                    # Internal wiring: parent worker drives/reads connectors
                    # Keep original reg/net tags from connectors()
                    pass
                else:
                    # Expose as I/O for testbench access
                    if sub_var.sig.is_input():
                        connector.tags.discard('reg')
                        connector.tags.discard('initializable')
                        connector.add_tag({'net', 'input'})
                        self.hdlmodule.add_input(AHDL_VAR((connector,), Ctx.LOAD))
                    elif sub_var.sig.is_output():
                        connector.add_tag('output')
                        self.hdlmodule.add_output(AHDL_VAR((connector,), Ctx.LOAD))

    def _process_fsm(self, fsm):
        scope = fsm.scope
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
            sig = self.hdlmodule.signal(p.sym)
            assert sig
            val = 0 if not p.defval else p.defval.value
            self.hdlmodule.parameters[sig] = val
        # Ensure submodule HDLModules have their I/O built first
        for _, subscope in self.hdlmodule.subscopes.items():
            if isinstance(subscope, HDLModule) and not getattr(subscope, '_built', False):
                sub_builder = HDLModuleBuilder.create(subscope)
                if sub_builder:
                    sub_builder.process(subscope)
                    subscope._built = True
        self._process_submodules()
        self._process_io(self.hdlmodule)

        self._collector.process(self.hdlmodule)
        fsms = list(self.hdlmodule.fsms.values())
        ctor_array_inits = []
        for fsm in fsms:
            if fsm.scope.is_ctor():
                self._add_roms(self._collector.mem_vars(fsm.name))
                # remove ctor fsm and add constant parameter assigns
                for stm in self._collect_moves(fsm):
                    if isinstance(stm.dst, AHDL_VAR) and stm.dst.sig.is_net():
                        assign = AHDL_ASSIGN(stm.dst, stm.src)
                        self.hdlmodule.add_static_assignment(assign, '')
                    elif isinstance(stm.dst, AHDL_SUBSCRIPT):
                        # Preserve array element initialization (e.g. ROM table init)
                        ctor_array_inits.append(stm)
                self.hdlmodule.remove_sig(fsm.state_var)
                del self.hdlmodule.fsms[fsm.name]
            else:
                self._process_fsm(fsm)
        # Add ctor array initialization to the first worker FSM's reset block
        if ctor_array_inits:
            for fsm in self.hdlmodule.fsms.values():
                for stm in ctor_array_inits:
                    self.hdlmodule.add_fsm_reset_stm(fsm.name, stm)
                break


class HDLTopModuleBuilderFlatten(HDLTopModuleBuilder):
    """Builder for module scopes in flatten compilation mode."""

    def _collect_internally_driven_inputs(self):
        """Collect input port signals that are written by any FSM via AHDL_IO_WRITE.

        In flatten mode, when one submodule writes to another submodule's input port,
        that port must become an internal reg rather than a top-level input.
        """
        targets = set()
        def walk(ahdl):
            if isinstance(ahdl, AHDL_IO_WRITE):
                if ahdl.io.sig.is_input() and ahdl.io.sig.is_single_port():
                    targets.add(id(ahdl.io.sig))
            elif isinstance(ahdl, AHDL_BLOCK):
                for c in ahdl.codes:
                    walk(c)
            elif isinstance(ahdl, AHDL_IF):
                for b in ahdl.blocks:
                    walk(b)
        for fsm in self.hdlmodule.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    walk(state.block)
        return targets

    def _process_io(self, hdlmodule):
        internally_driven_inputs = self._collect_internally_driven_inputs()

        def collect_io(topmodule, hdlmodule, prefix_qsig):
            for sig in hdlmodule.get_signals({'single_port'}, exclude_tags=None, with_base=True):
                if sig.is_input():
                    if id(sig) in internally_driven_inputs:
                        # Driven by another subscope's FSM — make internal reg
                        sig.tags.discard('input')
                        sig.tags.discard('net')
                        sig.tags.add('reg')
                        sig.tags.add('initializable')
                    else:
                        topmodule.add_input(AHDL_VAR(prefix_qsig + (sig,), Ctx.LOAD))
                elif sig.is_output():
                    topmodule.add_output(AHDL_VAR(prefix_qsig + (sig,), Ctx.LOAD))
            for sig in hdlmodule.get_signals({'subscope'}, exclude_tags=None):
                subscope = hdlmodule.subscopes[sig]
                collect_io(topmodule, subscope, prefix_qsig + (sig,))

        collect_io(self.hdlmodule, self.hdlmodule, tuple())

    def _build_module(self):
        assert self.hdlmodule.scope.is_module()
        assert self.hdlmodule.scope.is_class()
        if not self.hdlmodule.scope.is_instantiated():
            return
        for p in self.hdlmodule.scope.module_params:
            sig = self.hdlmodule.signal(p.sym)
            assert sig
            val = 0 if not p.defval else p.defval.value
            self.hdlmodule.parameters[sig] = val
        self._process_io(self.hdlmodule)

        self._collector.process(self.hdlmodule)
        fsms = list(self.hdlmodule.fsms.values())
        ctor_array_inits = []
        for fsm in fsms:
            if fsm.scope.is_ctor():
                self._add_roms(self._collector.mem_vars(fsm.name))
                # remove ctor fsm and add constant parameter assigns
                for stm in self._collect_moves(fsm):
                    if isinstance(stm.dst, AHDL_VAR) and stm.dst.sig.is_net():
                        assign = AHDL_ASSIGN(stm.dst, stm.src)
                        self.hdlmodule.add_static_assignment(assign, '')
                    elif isinstance(stm.dst, AHDL_SUBSCRIPT):
                        # Preserve array element initialization (e.g. ROM table init)
                        ctor_array_inits.append(stm)
                self.hdlmodule.remove_sig(fsm.state_var)
                del self.hdlmodule.fsms[fsm.name]
            else:
                self._process_fsm(fsm)
        # Add ctor array initialization to the first worker FSM's reset block
        if ctor_array_inits:
            for fsm in self.hdlmodule.fsms.values():
                for stm in ctor_array_inits:
                    self.hdlmodule.add_fsm_reset_stm(fsm.name, stm)
                break
