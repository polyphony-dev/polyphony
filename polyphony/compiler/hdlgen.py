from collections import deque
from .env import env
from .ir import Ctx, CONST
from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .hdlmoduleinfo import HDLModuleInfo
from .hdlmemport import HDLMemPortMaker, HDLRegArrayPortMaker
from .hdlinterface import *
from .memref import *
from logging import getLogger
logger = getLogger(__name__)


class HDLModuleBuilder(object):
    @classmethod
    def create(cls, scope):
        if scope.is_module():
            return HDLTopModuleBuilder()
        elif scope.is_class() or scope.is_method():
            return None
        elif scope.is_testbench():
            return HDLTestbenchBuilder()
        else:
            return HDLFunctionModuleBuilder()

    def process(self, scope):
        self.module_info = HDLModuleInfo(scope, scope.orig_name, scope.name)
        self._build_module(scope)
        scope.module_info = self.module_info

    def _add_state_constants(self, scope):
        i = 0
        for stg in scope.stgs:
            for state in stg.states:
                self.module_info.add_state_constant(state.name, i)
                i += 1

    def _add_input_ports(self, funcif, scope):
        if scope.is_method():
            params = scope.params[1:]
        else:
            params = scope.params
        for i, (sym, _, _) in enumerate(params):
            if sym.typ.is_int():
                funcif.add_data_in(sym.hdl_name(), sym.typ.get_width(), True)
            elif sym.typ.is_list():
                continue

    def _add_output_ports(self, funcif, scope):
        if scope.return_type.is_scalar():
            funcif.add_data_out('out_0', scope.return_type.get_width(), True)
        elif scope.return_type.is_seq():
            raise NotImplementedError('return of a suquence type is not implemented')

    def _add_internal_ports(self, scope, module_name, locals):
        regs = []
        nets = []
        for sig in locals:
            sig = scope.gen_sig(sig.name, sig.width, sig.tags)
            if sig.is_memif() or sig.is_ctrl() or sig.is_extport():
                continue
            elif sig.is_condition():
                self.module_info.add_internal_net(sig)
                nets.append(sig)
            else:
                assert ((sig.is_net() and not sig.is_reg()) or
                        (not sig.is_net() and sig.is_reg()) or
                        (not sig.is_net() and not sig.is_reg()))
                if sig.is_net():
                    self.module_info.add_internal_net(sig)
                    nets.append(sig)
                else:
                    self.module_info.add_internal_reg(sig)
                    regs.append(sig)
        return regs, nets

    def _add_state_register(self, fsm_name, scope, stgs):
        states_n = sum([len(stg.states) for stg in stgs])
        state_sig = scope.gen_sig(fsm_name + '_state', states_n.bit_length(), ['statevar'])
        self.module_info.add_fsm_state_var(fsm_name, state_sig)
        self.module_info.add_internal_reg(state_sig)

    def _add_submodules(self, scope):
        for callee_scope, inst_names in scope.callee_instances.items():
            if callee_scope.is_port():
                continue
            if callee_scope.is_lib():
                continue
            inst_scope_name = callee_scope.orig_name
            # TODO: add primitive function hook here
            if inst_scope_name == 'print':
                continue
            info = callee_scope.module_info
            for inst_name in inst_names:
                connections = []
                for inf in info.interfaces:
                    if not inf.name:
                        acc_name = inst_name
                    else:
                        acc_name = inst_name + '_' + inf.name
                    connections.append((inf, inf.accessor(acc_name)))
                self.module_info.add_sub_module(inst_name, info, connections)

    def _add_roms(self, scope):
        mrg = env.memref_graph
        roms = deque()

        roms.extend(mrg.collect_readonly_sink(scope))
        while roms:
            memnode = roms.pop()
            hdl_name = memnode.sym.hdl_name()
            source = memnode.single_source()
            if source:
                source_scope = list(source.scopes)[0]
                if source_scope.is_class():  # class field rom
                    hdl_name = source_scope.orig_name + '_field_' + hdl_name
            output_sig = scope.gen_sig(hdl_name, memnode.width)  # TODO
            fname = AHDL_VAR(output_sig, Ctx.STORE)
            input_sig = scope.gen_sig(hdl_name + '_in', memnode.width)  # TODO
            input = AHDL_VAR(input_sig, Ctx.LOAD)

            if source:
                array = source.initstm.src
                case_items = []
                for i, item in enumerate(array.items):
                    assert item.is_a(CONST)
                    connect = AHDL_CONNECT(fname, AHDL_CONST(item.value))
                    case_items.append(AHDL_CASE_ITEM(i, connect))
                case = AHDL_CASE(input, case_items)
            else:
                case_items = []
                n2o = memnode.pred_branch()
                for i, pred in enumerate(n2o.orig_preds):
                    assert pred.is_sink()
                    if scope not in pred.scopes:
                        roms.append(pred)
                    rom_func_name = pred.sym.hdl_name()
                    call = AHDL_FUNCALL(rom_func_name, [input])
                    connect = AHDL_CONNECT(fname, call)
                    case_val = '{}_cs[{}]'.format(hdl_name, i)
                    case_items.append(AHDL_CASE_ITEM(case_val, connect))
                rom_sel_sig = scope.gen_sig(hdl_name + '_cs', len(memnode.pred_ref_nodes()))
                case = AHDL_CASE(AHDL_SYMBOL('1\'b1'), case_items)
                self.module_info.add_internal_reg(rom_sel_sig)
            rom_func = AHDL_FUNCTION(fname, [input], [case])
            self.module_info.add_function(rom_func)

    def _rename_signal(self, scope):
        for input_sig in [sig for sig in scope.signals.values() if sig.is_input()]:
            if scope.is_method():
                new_name = '{}_{}_{}'.format(scope.parent.orig_name,
                                             scope.orig_name,
                                             input_sig.name)
            else:
                new_name = '{}_{}'.format(scope.orig_name, input_sig.name)
            scope.rename_sig(input_sig.name, new_name)
        for output_sig in [sig for sig in scope.signals.values() if sig.is_output()]:
            # TODO
            if scope.is_method():
                out_name = '{}_{}_out_0'.format(scope.parent.orig_name, scope.orig_name)
            else:
                out_name = '{}_out_0'.format(scope.orig_name)
            scope.rename_sig(output_sig.name, out_name)

    def _collect_vars(self, scope):
        outputs = set()
        defs = set()
        uses = set()
        collector = AHDLVarCollector(self.module_info, defs, uses, outputs)
        for stg in scope.stgs:
            for state in stg.states:
                for code in state.codes:
                    collector.visit(code)
        return defs, uses, outputs

    def _collect_special_decls(self, scope):
        edge_detectors = set()
        collector = AHDLSpecialDeclCollector(edge_detectors)
        for stg in scope.stgs:
            for state in stg.states:
                for code in state.codes:
                    collector.visit(code)
        return edge_detectors

    def _collect_moves(self, scope):
        moves = []
        for stg in scope.stgs:
            for state in stg.states:
                moves.extend([code for code in state.codes if code.is_a(AHDL_MOVE)])
        return moves


class HDLFunctionModuleBuilder(HDLModuleBuilder):
    def _build_module(self, scope):
        if scope.is_worker():
            return
        mrg = env.memref_graph

        if not scope.is_testbench():
            self._add_state_constants(scope)

        defs, uses, outputs = self._collect_vars(scope)
        locals = defs.union(uses)

        module_name = scope.stgs[0].name
        self._add_state_register(module_name, scope, scope.stgs)
        funcif = FunctionInterface('')
        self._add_input_ports(funcif, scope)
        self._add_output_ports(funcif, scope)
        self.module_info.add_interface(funcif)

        self._add_internal_ports(scope, module_name, locals)

        for memnode in mrg.collect_ram(scope):
            HDLMemPortMaker(memnode, scope, self.module_info).make_port()

        for memnode in mrg.collect_immutable(scope):
            if not memnode.is_writable():
                continue
            HDLRegArrayPortMaker(memnode, scope, self.module_info).make_port()

        self._add_submodules(scope)
        self._add_roms(scope)
        self.module_info.add_fsm_stg(scope.orig_name, scope.stgs)
        for d in defs:
            if d.is_reg():
                clear_var = AHDL_MOVE(AHDL_VAR(d, Ctx.STORE), AHDL_CONST(0))
                self.module_info.add_fsm_reset_stm(scope.orig_name, clear_var)

        self._rename_signal(scope)


class HDLTestbenchBuilder(HDLModuleBuilder):
    def _build_module(self, scope):
        mrg = env.memref_graph

        if not scope.is_testbench():
            self._add_state_constants(scope)

        defs, uses, outputs = self._collect_vars(scope)
        locals = defs.union(uses)

        module_name = scope.stgs[0].name
        self._add_internal_ports(scope, module_name, locals)

        for memnode in mrg.collect_ram(scope):
            HDLMemPortMaker(memnode, scope, self.module_info).make_port()

        for memnode in mrg.collect_immutable(scope):
            if not memnode.is_writable():
                continue
            HDLRegArrayPortMaker(memnode, scope, self.module_info).make_port()

        self._add_submodules(scope)
        for sym, cp, _ in scope.params:
            if sym.typ.is_object() and sym.typ.get_scope().is_module():
                mod_scope = sym.typ.get_scope()
                info = mod_scope.module_info
                if info.interfaces:
                    accessor = info.interfaces[0].accessor(cp.name)
                    connections = [(info.interfaces[0], accessor)]
                else:
                    connections = []
                self.module_info.add_sub_module(cp.name, info, connections)

        self._add_roms(scope)
        self.module_info.add_fsm_stg(scope.orig_name, scope.stgs)
        for d in defs:
            if d.is_reg():
                clear_var = AHDL_MOVE(AHDL_VAR(d, Ctx.STORE), AHDL_CONST(0))
                self.module_info.add_fsm_reset_stm(scope.orig_name, clear_var)

        edge_detectors = self._collect_special_decls(scope)
        for sig, old, new in edge_detectors:
            self.module_info.add_edge_detector(sig, old, new)

        self._rename_signal(scope)


class HDLTopModuleBuilder(HDLModuleBuilder):

    def _process_io(self, module_scope):
        inf = PlainInterface(module_scope.orig_name, False, True)
        self.module_info.add_interface(inf)
        iports = []
        oports = []
        for field in sorted(module_scope.class_fields().values()):
            if field.typ.is_port():
                p_scope = field.typ.get_scope()
                assert p_scope.is_port()
                signed = True if p_scope.name == 'polyphony.io.Int' else False
                port_t = field.typ
                width = port_t.get_width()
                if port_t.get_direction() == 'input':
                    iports.append(Port(field.name, width, 'in', signed))
                elif port_t.get_direction() == 'output':
                    oports.append(Port(field.name, width, 'out', signed))
                else:
                    assert False
        inf.ports.extend(iports)
        inf.ports.extend(oports)

    def _process_worker(self, module_scope, worker, reset_stms):
        mrg = env.memref_graph

        self._add_state_constants(worker)
        defs, uses, outputs = self._collect_vars(worker)
        locals = defs.union(uses)
        regs, nets = self._add_internal_ports(module_scope, module_scope.orig_name, locals)
        self._add_state_register(worker.orig_name, module_scope, worker.stgs)

        self._add_submodules(worker)
        for memnode in mrg.collect_ram(worker):
            memportmaker = HDLMemPortMaker(memnode, worker, self.module_info).make_port()

        self._add_roms(worker)

        self.module_info.add_fsm_stg(worker.orig_name, worker.stgs)
        for stm in reset_stms:
            if stm.dst.sig in defs or stm.dst.sig in outputs:
                self.module_info.add_fsm_reset_stm(worker.orig_name, stm)
        for reg in regs:
            clear_var = AHDL_MOVE(AHDL_VAR(reg, Ctx.STORE), AHDL_CONST(0))
            self.module_info.add_fsm_reset_stm(worker.orig_name, clear_var)

        edge_detectors = self._collect_special_decls(worker)
        for sig, old, new in edge_detectors:
            self.module_info.add_edge_detector(sig, old, new)

    def _build_module(self, scope):
        assert scope.is_module()
        assert scope.is_class()

        reset_stms = set()
        for s in scope.children:
            if s.is_ctor():
                # TODO parse for reset signal
                reset_stms = self._collect_field_defs(s)
                break

        self._process_io(scope)
        for worker, args in scope.workers:
            self._process_worker(scope, worker, reset_stms)

    def _collect_field_defs(self, scope):
        moves = self._collect_moves(scope)
        defs = []
        for mv in moves:
            if mv.dst.is_a(AHDL_VAR) and mv.dst.sig.is_output():
                defs.append(mv)
        return defs


class AHDLVarCollector(AHDLVisitor):
    '''this class collects inputs and outputs and locals'''
    def __init__(self, module_info, local_defs, local_uses, output_temps):
        self.local_defs = local_defs
        self.local_uses = local_uses
        self.output_temps = output_temps
        self.module_constants = [c for c, _ in module_info.state_constants]

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig.is_ctrl() or ahdl.sig.is_input() or ahdl.sig.name in self.module_constants:
            pass
        elif ahdl.sig.is_output():
            self.output_temps.add(ahdl.sig)
        else:
            if ahdl.ctx & Ctx.STORE:
                self.local_defs.add(ahdl.sig)
            else:
                self.local_uses.add(ahdl.sig)
        #else:
        #    text = ahdl.sym.name #get_src_text(ir)
        #    raise RuntimeError('free variable is not supported yet.\n' + text)


class AHDLSpecialDeclCollector(AHDLVisitor):
    def __init__(self, edge_detectors):
        self.edge_detectors = edge_detectors

    def visit_WAIT_EDGE(self, ahdl):
        old, new = ahdl.args[0], ahdl.args[1]
        for var in ahdl.args[2:]:
            self.edge_detectors.add((var.sig, old, new))
            if ahdl.codes:
                for code in ahdl.codes:
                    self.visit(code)
