from collections import deque
from .env import env
from .ir import Ctx, CONST
from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .hdlmoduleinfo import HDLModuleInfo, FIFOModuleInfo
from .hdlmemport import HDLMemPortMaker, HDLRegArrayPortMaker
from .hdlinterface import *
from .memref import *
from logging import getLogger
logger = getLogger(__name__)


class HDLModuleBuilder(object):
    @classmethod
    def create(cls, scope):
        if scope.is_global():
            return None
        elif scope.is_module():
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
                elif sig.is_reg():
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
                for inf in info.interfaces.values():
                    acc = inf.accessor(inst_name)
                    connections.append((inf, acc))
                    self.module_info.add_accessor(acc.acc_name, acc)
                self.module_info.add_sub_module(inst_name, info, connections)

    def _add_roms(self, scope):
        mrg = env.memref_graph
        roms = deque()

        roms.extend(mrg.collect_readonly_sink(scope))
        while roms:
            memnode = roms.pop()
            hdl_name = memnode.sym.hdl_name()
            if scope.is_worker():
                hdl_name = '{}_{}'.format(scope.orig_name, hdl_name)
            source = memnode.single_source()
            if source:
                source_scope = list(source.scopes)[0]
                if source_scope.is_class():  # class field rom
                    hdl_name = source_scope.orig_name + '_field_' + hdl_name
            output_sig = scope.gen_sig(hdl_name, memnode.data_width())  # TODO
            fname = AHDL_VAR(output_sig, Ctx.STORE)
            input_sig = scope.gen_sig(hdl_name + '_in', memnode.data_width())  # TODO
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
                    call = AHDL_FUNCALL(AHDL_SYMBOL(rom_func_name), [input])
                    connect = AHDL_CONNECT(fname, call)
                    case_val = '{}_cs[{}]'.format(hdl_name, i)
                    case_items.append(AHDL_CASE_ITEM(case_val, connect))
                rom_sel_sig = scope.gen_sig(hdl_name + '_cs', len(memnode.pred_ref_nodes()))
                case = AHDL_CASE(AHDL_SYMBOL('1\'b1'), case_items)
                self.module_info.add_internal_reg(rom_sel_sig)
            rom_func = AHDL_FUNCTION(fname, [input], [case])
            self.module_info.add_function(rom_func)

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

    def _add_seq_interface(self, signal):
        if signal.is_fifo_port():
            if signal.is_input():
                inf = FIFOReadInterface(signal)
            elif signal.is_output():
                inf = FIFOWriteInterface(signal)
            else:
                # internal fifo
                return
        else:
            assert False
        self.module_info.add_interface(inf.if_name, inf)

    def _add_single_port_interface(self, signal):
        if signal.is_input():
            inf = SingleReadInterface(signal)
        elif signal.is_output():
            inf = SingleWriteInterface(signal)
        else:
            # internal single port
            return
        self.module_info.add_interface(inf.if_name, inf)


class HDLFunctionModuleBuilder(HDLModuleBuilder):
    def _build_module(self, scope):
        if scope.is_worker():
            return
        mrg = env.memref_graph

        self._add_state_constants(scope)

        defs, uses, outputs = self._collect_vars(scope)
        locals = defs.union(uses)

        module_name = scope.stgs[0].name
        self._add_state_register(module_name, scope, scope.stgs)
        callif = CallInterface('', module_name)
        self.module_info.add_interface('', callif)
        self._add_input_interfaces(scope)
        self._add_output_interfaces(scope)
        self._add_internal_ports(scope, module_name, locals)

        HDLMemPortMaker(mrg.collect_ram(scope), scope, self.module_info).make_port_all()

        for memnode in mrg.collect_immutable(scope):
            if not memnode.is_writable():
                continue
            HDLRegArrayPortMaker(memnode, scope, self.module_info).make_port()

        self._add_submodules(scope)
        self._add_roms(scope)
        self.module_info.add_fsm_stg(scope.orig_name, scope.stgs)
        self._add_reset_stms_for_func(scope, defs, uses, outputs)

    def _add_reset_stms_for_func(self, worker, defs, uses, outputs):
        for inf in self.module_info.interfaces.values():
            for stm in inf.reset_stms():
                self.module_info.add_fsm_reset_stm(worker.orig_name, stm)
        for sig in uses:
            if sig not in defs:
                local_accessors = self.module_info.local_readers.values()
                accs = [acc for acc in local_accessors if acc.inf.signal is sig]
                for acc in accs:
                    for stm in acc.reset_stms():
                        self.module_info.add_fsm_reset_stm(worker.orig_name, stm)
        for sig in defs:
            # reset internal ports
            if sig.is_memif():
                local_accessors = self.module_info.local_writers.values()
                accs = [acc for acc in local_accessors if acc.inf.signal is sig]
                for acc in accs:
                    for stm in acc.reset_stms():
                        self.module_info.add_fsm_reset_stm(worker.orig_name, stm)
            # reset internal regs
            elif sig.is_reg():
                if sig.is_initializable():
                    v = AHDL_CONST(sig.init_value)
                else:
                    v = AHDL_CONST(0)
                mv = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), v)
                self.module_info.add_fsm_reset_stm(worker.orig_name, mv)

    def _add_input_interfaces(self, scope):
        if scope.is_method():
            assert False
            params = scope.params[1:]
        else:
            params = scope.params
        for i, (sym, _, _) in enumerate(params):
            if sym.typ.is_int() or sym.typ.is_bool():
                sig_name = '{}_{}'.format(scope.orig_name, sym.hdl_name())
                sig = scope.signal(sig_name)
                inf = SingleReadInterface(sig, sym.hdl_name(), scope.orig_name)
            elif sym.typ.is_list():
                memnode = sym.typ.get_memnode()
                inf = RAMBridgeInterface(memnode.name(),
                                         self.module_info.name,
                                         memnode.data_width(),
                                         memnode.addr_width())
                self.module_info.node2if[memnode] = inf
            elif sym.typ.is_tuple():
                memnode = sym.typ.get_memnode()
                inf = RegArrayInterface(memnode.name(),
                                        self.module_info.name,
                                        memnode.data_width(),
                                        memnode.length)
            else:
                assert False
            self.module_info.add_interface(inf.if_name, inf)

    def _add_output_interfaces(self, scope):
        if scope.return_type.is_scalar():
            sig_name = '{}_out_0'.format(scope.orig_name)
            sig = scope.signal(sig_name)
            inf = SingleWriteInterface(sig, 'out_0', scope.orig_name)
            self.module_info.add_interface(inf.if_name, inf)
        elif scope.return_type.is_seq():
            raise NotImplementedError('return of a suquence type is not implemented')


def accessor2module(acc):
    if isinstance(acc, FIFOWriteAccessor) or isinstance(acc, FIFOReadAccessor):
        return FIFOModuleInfo(acc.inf.signal)
    return None


class HDLTestbenchBuilder(HDLModuleBuilder):
    def _build_module(self, scope):
        mrg = env.memref_graph

        self._add_state_constants(scope)

        defs, uses, outputs = self._collect_vars(scope)
        locals = defs.union(uses)

        module_name = scope.stgs[0].name
        self._add_state_register(module_name, scope, scope.stgs)
        self._add_internal_ports(scope, module_name, locals)

        HDLMemPortMaker(mrg.collect_ram(scope), scope, self.module_info).make_port_all()

        for memnode in mrg.collect_immutable(scope):
            if not memnode.is_writable():
                continue
            HDLRegArrayPortMaker(memnode, scope, self.module_info).make_port()

        self._add_submodules(scope)
        for sym, cp, _ in scope.params:
            if sym.typ.is_object() and sym.typ.get_scope().is_module():
                mod_scope = sym.typ.get_scope()
                info = mod_scope.module_info
                connections = []
                for inf in info.interfaces.values():
                    accessor = inf.accessor(cp.name)
                    connections.append((inf, accessor))
                    self.module_info.add_accessor(accessor.acc_name, accessor)
                self.module_info.add_sub_module(cp.name, info, connections)
        for acc in self.module_info.accessors.values():
            acc_mod = accessor2module(acc)
            if acc_mod:
                connections = []
                for inf in acc_mod.interfaces.values():
                    inf_acc = inf.accessor(acc.inst_name)
                    connections.append((inf, inf_acc))
                    self.module_info.add_sub_module(inf_acc.acc_name, acc_mod, connections, acc_mod.param_map)
            for stm in acc.reset_stms():
                self.module_info.add_fsm_reset_stm(scope.orig_name, stm)

        self._add_roms(scope)
        self.module_info.add_fsm_stg(scope.orig_name, scope.stgs)
        for d in defs:
            if d.is_reg():
                clear_var = AHDL_MOVE(AHDL_VAR(d, Ctx.STORE), AHDL_CONST(0))
                self.module_info.add_fsm_reset_stm(scope.orig_name, clear_var)

        edge_detectors = self._collect_special_decls(scope)
        for sig, old, new in edge_detectors:
            self.module_info.add_edge_detector(sig, old, new)


class HDLTopModuleBuilder(HDLModuleBuilder):
    def _process_io(self, module_scope):
        signals = module_scope.get_signals()
        for sig in signals.values():
            if sig.is_single_port():
                self._add_single_port_interface(sig)
            elif sig.is_seq_port():
                self._add_seq_interface(sig)

    def _process_connector_port(self, module_scope):
        signals = module_scope.get_signals()
        for sig in signals.values():
            if sig.is_input() or sig.is_output():
                continue
            if sig.is_single_port() or sig.is_seq_port():
                self._add_connector_port(sig)

    def _add_connector_port(self, signal):
        if signal.is_single_port():
            reader = SingleWriteInterface(signal).accessor('')
            writer = SingleReadInterface(signal).accessor('')
            self.module_info.add_local_reader(reader.acc_name, reader)
            self.module_info.add_local_writer(writer.acc_name, writer)
            ports = reader.regs() + writer.regs()
            for p in ports:
                name = reader.port_name(p)
                sig = self.module_info.scope.gen_sig(name, p.width)
                self.module_info.add_internal_reg(sig)
        else:
            if signal.is_fifo_port():
                mod = FIFOModuleInfo(signal)
            else:
                assert False
            reader = FIFOWriteInterface(signal).accessor('')
            writer = FIFOReadInterface(signal).accessor('')
            self.module_info.add_local_reader(reader.acc_name, reader)
            self.module_info.add_local_writer(writer.acc_name, writer)
            acc = mod.inf.accessor('')
            self.module_info.add_accessor(acc.acc_name, acc)
            connections = [(mod.inf, acc)]
            self.module_info.add_sub_module(signal.name, mod, connections, mod.param_map)
            ports = reader.ports.all() + writer.ports.all()
            for p in ports:
                name = reader.port_name(p)
                sig = self.module_info.scope.gen_sig(name, p.width)
                if p.dir == 'in':
                    self.module_info.add_internal_reg(sig)
                else:
                    self.module_info.add_internal_net(sig)

    def _process_worker(self, module_scope, worker, reset_stms):
        mrg = env.memref_graph

        self._add_state_constants(worker)
        defs, uses, outputs = self._collect_vars(worker)
        locals = defs.union(uses)
        regs, nets = self._add_internal_ports(module_scope, module_scope.orig_name, locals)
        self._add_state_register(worker.orig_name, module_scope, worker.stgs)

        self._add_submodules(worker)
        HDLMemPortMaker(mrg.collect_ram(worker), worker, self.module_info).make_port_all()

        self._add_roms(worker)
        self.module_info.add_fsm_stg(worker.orig_name, worker.stgs)
        self._add_reset_stms_for_worker(worker, defs, uses, outputs)
        edge_detectors = self._collect_special_decls(worker)
        for sig, old, new in edge_detectors:
            self.module_info.add_edge_detector(sig, old, new)

    def _add_reset_stms_for_worker(self, worker, defs, uses, outputs):
        for sig in outputs:
            # reset output ports
            infs = [inf for inf in self.module_info.interfaces.values() if inf.signal is sig]
            for inf in infs:
                for stm in inf.reset_stms():
                    self.module_info.add_fsm_reset_stm(worker.orig_name, stm)
        for sig in uses:
            if sig.is_seq_port() or sig.is_single_port():
                local_accessors = self.module_info.local_readers.values()
                accs = [acc for acc in local_accessors if acc.inf.signal is sig]
                for acc in accs:
                    for stm in acc.reset_stms():
                        self.module_info.add_fsm_reset_stm(worker.orig_name, stm)
        for sig in defs:
            # reset internal ports
            if sig.is_seq_port() or sig.is_single_port():
                local_accessors = self.module_info.local_writers.values()
                accs = [acc for acc in local_accessors if acc.inf.signal is sig]
                for acc in accs:
                    for stm in acc.reset_stms():
                        self.module_info.add_fsm_reset_stm(worker.orig_name, stm)
            # reset internal regs
            elif sig.is_reg():
                if sig.is_initializable():
                    v = AHDL_CONST(sig.init_value)
                else:
                    v = AHDL_CONST(0)
                mv = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), v)
                self.module_info.add_fsm_reset_stm(worker.orig_name, mv)

    def _build_module(self, scope):
        assert scope.is_module()
        assert scope.is_class()

        reset_stms = []
        for s in scope.children:
            if s.is_ctor():
                reset_stms.extend(self._collect_module_defs(s))
                break

        self._process_io(scope)
        self._process_connector_port(scope)
        for worker, _ in scope.workers:
            self._process_worker(scope, worker, reset_stms)
        for stm in reset_stms:
            if stm.dst.sig.is_field():
                assign = AHDL_ASSIGN(stm.dst, stm.src)
                self.module_info.add_static_assignment(assign, '')
                self.module_info.add_internal_net(stm.dst.sig, '')

    def _collect_module_defs(self, scope):
        moves = self._collect_moves(scope)
        defs = []
        for mv in moves:
            if (mv.dst.is_a(AHDL_VAR) and
                    (mv.dst.sig.is_output() or
                     mv.dst.sig.is_field())):
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

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.ctx & Ctx.STORE:
            self.local_defs.add(ahdl.sig)
        else:
            self.local_uses.add(ahdl.sig)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig.is_ctrl() or ahdl.sig.name in self.module_constants:
            pass
        elif ahdl.sig.is_field():
            pass
        elif ahdl.sig.is_extport():
            pass
        elif ahdl.sig.is_input():
            if ahdl.sig.is_seq_port():
                self.output_temps.add(ahdl.sig)
            elif ahdl.sig.is_single_port():
                self.output_temps.add(ahdl.sig)
        elif ahdl.sig.is_output():
            self.output_temps.add(ahdl.sig)
        else:
            if ahdl.ctx & Ctx.STORE:
                self.local_defs.add(ahdl.sig)
            else:
                self.local_uses.add(ahdl.sig)


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
