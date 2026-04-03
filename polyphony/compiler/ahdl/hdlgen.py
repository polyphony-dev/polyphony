
from .ahdl import *
from .stg import STG
from .transformers.varcollector import AHDLVarCollector
from .transformers.varreplacer import AHDLSignalReplacer
from .hdlmodule import FSM, HDLModule
from ..common.env import env
from ..common.errors import Errors, CompileError
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

    @staticmethod
    def _is_protocol_module(subscope):
        """A protocol module is a module with NO logic after compilation —
        no FSMs, no port-driving decls, no sub_modules.  Its methods are
        inlined into the caller.  E.g. Handshake, RAMPort, FIFOPort,
        and workerless submodules with only parameter fields."""
        if not isinstance(subscope, HDLModule):
            return False
        if subscope.fsms or subscope.sub_modules:
            return False
        # Decls that write to port signals are real combinational logic
        # (e.g. Port.assign). Decls that only set parameter constants are fine.
        for decl in subscope.decls:
            if isinstance(decl, AHDL_ASSIGN) and decl.dst.sig.is_single_port():
                return False
        return True

    @staticmethod
    def _is_inlinelib_module(subscope):
        """An inlinelib module has its methods inlined into callers but
        retains internal workers (FSMs).  It must be fully merged into
        the parent in individual compilation mode."""
        if not isinstance(subscope, HDLModule):
            return False
        return subscope.scope.is_inlinelib()

    def _process_submodules(self):
        for instance_sig, subscope in self.hdlmodule.subscopes.items():
            if not isinstance(subscope, HDLModule):
                continue
            if self._is_inlinelib_module(subscope):
                self._process_inlinelib_subscope(instance_sig, subscope)
            elif self._is_protocol_module(subscope):
                self._process_protocol_subscope(instance_sig, subscope)
            else:
                self._process_regular_subscope(instance_sig, subscope)

    def _process_inlinelib_subscope(self, instance_sig, subscope):
        """Fully inline an @inlinelib submodule into the parent module.

        The submodule's FSMs and declarations are merged into the parent,
        with all signal references remapped to nested form so that
        FlattenSignalsIndividual can flatten them later.
        """
        # Collect state var signals so we can handle them specially
        state_var_sigs = {fsm.state_var for fsm in subscope.fsms.values()}

        # Build replace table
        replace_table: dict[tuple, tuple] = {}
        flat_state_vars: dict[Signal, Signal] = {}
        for sig_name, sig in subscope.signals.items():
            if sig_name in ('clk', 'rst'):
                continue
            if sig in state_var_sigs:
                # State vars: create a flat signal in the parent to avoid
                # mismatch between fsm.state_var and STG references
                flat_name = f'{instance_sig.name}_{sig_name}'
                flat_sig = self.hdlmodule.gen_sig(flat_name, sig.width, sig.tags)
                replace_table[(sig,)] = (flat_sig,)
                flat_state_vars[sig] = flat_sig
            else:
                # All other signals: nest under instance_sig
                replace_table[(sig,)] = (instance_sig, sig)

        replacer = AHDLSignalReplacer(replace_table)
        replacer.hdlmodule = self.hdlmodule

        # Merge FSMs: create shallow copies so the Channel originals are untouched.
        # Prefix FSM names with the instance name to avoid collisions
        # when multiple instances of the same @inlinelib module exist.
        prefix = instance_sig.name
        for fsm_name, fsm in subscope.fsms.items():
            merged_name = f'{prefix}_{fsm_name}'
            new_state_var = flat_state_vars.get(fsm.state_var, fsm.state_var)
            new_fsm = FSM(merged_name, fsm.scope, new_state_var)
            for stg in fsm.stgs:
                new_stg = STG(stg.name, stg.parent, self.hdlmodule)
                new_stg.set_states(list(stg.states))
                new_stg.scheduling = stg.scheduling
                new_fsm.stgs.append(new_stg)
            new_fsm.outputs = fsm.outputs.copy()
            new_fsm.reset_stms = fsm.reset_stms[:]
            replacer.process_fsm(new_fsm)
            # Keep only array-element resets (from ctor init);
            # _process_fsm will re-add scalar reg resets later.
            new_fsm.reset_stms = [
                stm for stm in new_fsm.reset_stms
                if isinstance(stm, AHDL_MOVE) and isinstance(stm.dst, AHDL_SUBSCRIPT)
            ]
            self.hdlmodule.fsms[merged_name] = new_fsm

        # Merge declarations (combinational assigns)
        for decl in subscope.decls:
            new_decl = replacer.visit(decl)
            if isinstance(new_decl, AHDL_DECL):
                self.hdlmodule.add_decl(new_decl)

        # Mark as inlined so Verilog output skips this module
        subscope._inlined_into_parent = True
        logger.debug(str(self.hdlmodule))

    def _process_protocol_subscope(self, instance_sig, subscope):
        """Flatten a protocol module's ports into the parent module."""
        replace_table:dict[tuple, tuple] = {}
        for var in subscope._inputs + subscope._outputs:
            # Flip tags: parent drives child outputs, reads child inputs
            if var.sig.is_output():
                attrs = {'connector', 'reg', 'initializable'}
            else:
                attrs = {'connector', 'net'}
            if var.sig.is_ctrl():
                attrs.add('ctrl')
            connector_name = f'{instance_sig.name}_{var.hdl_name}'
            connector = self.hdlmodule.gen_sig(connector_name, var.sig.width, attrs)
            self.hdlmodule.protocol_ports.append((instance_sig, var, connector))
            nested_vars = (instance_sig,) + var.vars
            replace_table[nested_vars] = (connector,)
        # Migrate constant parameter decls to parent module
        for decl in subscope.decls:
            if isinstance(decl, AHDL_ASSIGN):
                # Re-create the signal in the parent with prefixed name
                dst_name = f'{instance_sig.name}_{decl.dst.hdl_name}'
                dst_sig = self.hdlmodule.gen_sig(dst_name, decl.dst.sig.width, decl.dst.sig.tags)
                new_dst = AHDL_VAR(dst_sig, Ctx.STORE)
                self.hdlmodule.add_static_assignment(AHDL_ASSIGN(new_dst, decl.src))
                # Also replace references to the param in parent FSMs
                nested_param = (instance_sig,) + decl.dst.vars
                replace_table[nested_param] = (dst_sig,)
        AHDLSignalReplacer(replace_table).process(self.hdlmodule)
        logger.debug(str(self.hdlmodule))

    def _process_regular_subscope(self, instance_sig, subscope):
        """Existing behavior for regular submodules with workers."""
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
        replace_table:dict[tuple, tuple] = {}
        for var, connector in connections:
            vars = (instance_sig,) + var.vars
            replace_table[vars] = (connector,)
        AHDLSignalReplacer(replace_table).process(self.hdlmodule)
        self._regular_subscope_instances.append(instance_sig)
        logger.debug(str(self.hdlmodule))

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
        # Protocol ports are always exposed as parent I/O
        # (they represent the parent's external interface, not internal wiring)
        for _proto_sig, sub_var, connector in self.hdlmodule.protocol_ports:
            connector.width = sub_var.sig.width
            if sub_var.sig.is_int():
                connector.add_tag('int')
            if sub_var.sig.is_output():
                # Child output → parent output (parent FSM drives it)
                connector.add_tag('output')
                connector.add_tag('single_port')
                self.hdlmodule.add_output(AHDL_VAR((connector,), Ctx.STORE))
            elif sub_var.sig.is_input():
                # Child input → parent input (external provides it)
                connector.tags.discard('net')
                connector.add_tag({'net', 'input', 'single_port'})
                self.hdlmodule.add_input(AHDL_VAR((connector,), Ctx.LOAD))

    def _check_internal_field_access(self):
        """After I/O port references are replaced with connectors,
        check that no parent FSM/decl still references internal fields
        of a regular submodule.  Such references indicate that inlined
        methods wrote to submodule fields — which cannot be compiled
        as separate modules."""
        if not self._regular_subscope_instances:
            return
        regular_sigs = set(self._regular_subscope_instances)
        # Collect all nested var references from the collector
        all_nested = self._collector.submodule_vars()
        for vars in all_nested:
            if vars[0] in regular_sigs:
                field_name = vars[-1].name
                instance_name = vars[0].name
                msg = str(Errors.SUBMODULE_INTERNAL_FIELD_ACCESS).format(
                    field_name, instance_name)
                raise CompileError(msg)

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
        self._regular_subscope_instances = []
        self._process_submodules()
        self._process_io(self.hdlmodule)

        self._collector.process(self.hdlmodule)
        self._check_internal_field_access()
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
                # Skip submodules with workers — their ports are internal signals
                if subscope.scope.is_module() and len(subscope.scope.workers) > 0:
                    self._internalize_ports(subscope)
                    continue
                collect_io(topmodule, subscope, prefix_qsig + (sig,))

        collect_io(self.hdlmodule, self.hdlmodule, tuple())

    def _internalize_ports(self, hdlscope):
        """Convert all port signals in a submodule scope to internal reg/net."""
        for sig in hdlscope.get_signals({'single_port'}, exclude_tags=None, with_base=True):
            sig.tags.discard('input')
            sig.tags.discard('output')
            sig.tags.discard('single_port')
            if 'net' in sig.tags:
                sig.tags.discard('net')
                sig.tags.add('reg')
                sig.tags.add('initializable')
        for sig in hdlscope.get_signals({'subscope'}, exclude_tags=None):
            subscope = hdlscope.subscopes[sig]
            self._internalize_ports(subscope)

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
