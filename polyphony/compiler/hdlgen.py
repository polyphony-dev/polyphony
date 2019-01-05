from collections import defaultdict, deque
from .env import env
from .ir import Ctx, CONST
from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .hdlmodule import FIFOModule
from .hdlmemport import HDLMemPortMaker, HDLTuplePortMaker, HDLRegArrayPortMaker
from .hdlinterface import *
from .memref import *
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

    def _add_state_constants(self, fsm):
        i = 0
        for stg in fsm.stgs:
            for state in stg.states:
                self.hdlmodule.add_state_constant(state.name, i)
                i += 1

    def _add_internal_ports(self, locals):
        regs = []
        nets = []
        for sig in locals:
            sig = self.hdlmodule.gen_sig(sig.name, sig.width, sig.tags)
            if sig.is_memif() or sig.is_ctrl() or sig.is_extport():
                continue
            else:
                assert ((sig.is_net() and not sig.is_reg()) or
                        (not sig.is_net() and sig.is_reg()) or
                        (not sig.is_net() and not sig.is_reg()))
                if sig.is_net():
                    self.hdlmodule.add_internal_net(sig)
                    nets.append(sig)
                elif sig.is_reg():
                    self.hdlmodule.add_internal_reg(sig)
                    regs.append(sig)
        return regs, nets

    def _add_state_register(self, fsm):
        states_n = sum([len(stg.states) for stg in fsm.stgs])
        state_sig = self.hdlmodule.gen_sig(fsm.name + '_state', states_n.bit_length(), ['statevar'])
        self.hdlmodule.add_fsm_state_var(fsm.name, state_sig)
        self.hdlmodule.add_internal_reg(state_sig)

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
            self._add_submodule_instances(env.hdlmodule(callee_scope), inst_names, {})

    def _add_submodule_instances(self, sub_hdlmodule, inst_names, param_map, is_internal=False):
        for inst_name in inst_names:
            connections = defaultdict(list)
            for sub_module_inf in sub_hdlmodule.interfaces.values():
                if is_internal:
                    acc = sub_module_inf.accessor('')
                else:
                    acc = sub_module_inf.accessor(inst_name)
                    self._add_external_accessor_for_submodule(sub_module_inf, acc)
                if isinstance(sub_module_inf, WriteInterface):
                    connections['ret'].append((sub_module_inf, acc))
                else:
                    connections[''].append((sub_module_inf, acc))
            self.hdlmodule.add_sub_module(inst_name, sub_hdlmodule, connections, param_map=param_map)

    def _add_external_accessor_for_submodule(self, sub_module_inf, acc):
        if not isinstance(acc, CallAccessor) and acc.acc_name not in self.hdlmodule.signals:
            # we have never accessed this interface
            return
        self.hdlmodule.add_accessor(acc.acc_name, acc)
        # deal with pipelined single port
        if sub_module_inf.signal and sub_module_inf.signal.is_single_port():
            acc_signal = self.hdlmodule.signals[acc.acc_name]
            # we should check acc_signal for the context of caller (it is accessed in pipeline or not)
            if acc_signal.is_pipelined_port() and sub_module_inf.signal.is_adaptered():
                adapter_name = '{}_{}'.format(acc.inst_name, sub_module_inf.signal.adapter_sig.name)
                adapter_sig = self.hdlmodule.gen_sig(adapter_name, sub_module_inf.signal.width)
                self._add_fifo_channel(adapter_sig)
                if sub_module_inf.signal.is_input():
                    item = single_output_port_fifo_adapter(self.hdlmodule, sub_module_inf.signal, acc.inst_name)
                else:
                    item = single_input_port_fifo_adapter(self.hdlmodule, sub_module_inf.signal, acc.inst_name)
                self.hdlmodule.add_decl('', item)

    def _add_roms(self, memnodes):
        mrg = env.memref_graph
        roms = [n for n in memnodes if mrg.is_readonly_sink(n)]
        while roms:
            memnode = roms.pop()
            hdl_name = memnode.name()
            source = memnode.single_source()
            if source:
                source_scope = source.scope
                if source_scope.is_class():  # class field rom
                    hdl_name = source_scope.orig_name + '_field_' + hdl_name
            output_sig = self.hdlmodule.gen_sig(hdl_name, memnode.data_width())  # TODO
            fname = AHDL_VAR(output_sig, Ctx.STORE)
            input_sig = self.hdlmodule.gen_sig(hdl_name + '_in', memnode.data_width())  # TODO
            input = AHDL_VAR(input_sig, Ctx.LOAD)

            if source:
                array = source.initstm.src
                case_items = []
                for i, item in enumerate(array.items):
                    assert item.is_a(CONST)
                    connect = AHDL_BLOCK(str(i), [AHDL_CONNECT(fname, AHDL_CONST(item.value))])
                    case_items.append(AHDL_CASE_ITEM(i, connect))
                case = AHDL_CASE(input, case_items)
                rom_func = AHDL_FUNCTION(fname, [input], [case])
            else:
                cs_name = hdl_name + '_cs'
                cs_sig = self.hdlmodule.signal(cs_name)
                assert cs_sig
                cs = AHDL_VAR(cs_sig, Ctx.LOAD)

                case_items = []
                n2o = memnode.pred_branch()
                for i, pred in enumerate(n2o.preds):
                    pred_root = mrg.find_nearest_single_source(pred)
                    assert len(pred_root.succs) == 1
                    for romsrc in pred_root.succs[0].succs:
                        if romsrc.is_sink():
                            break
                    else:
                        assert False
                    roms.append(romsrc)
                    rom_func_name = romsrc.sym.hdl_name()
                    call = AHDL_FUNCALL(AHDL_SYMBOL(rom_func_name), [input])
                    connect = AHDL_BLOCK(str(i), [AHDL_CONNECT(fname, call)])
                    case_val = '{}[{}]'.format(cs_name, i)
                    case_items.append(AHDL_CASE_ITEM(case_val, connect))
                case = AHDL_CASE(AHDL_SYMBOL('1\'b1'), case_items)
                rom_func = AHDL_FUNCTION(fname, [input, cs], [case])
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

    def _collect_special_decls(self, fsm):
        edge_detectors = set()
        collector = AHDLSpecialDeclCollector(edge_detectors)
        for stg in fsm.stgs:
            for state in stg.states:
                collector.visit(state)
        return edge_detectors

    def _collect_moves(self, fsm):
        moves = []
        for stg in fsm.stgs:
            for state in stg.states:
                moves.extend([code for code in state.traverse() if code.is_a(AHDL_MOVE)])
        return moves

    def _add_seq_interface(self, signal):
        inf = create_seq_interface(signal)
        if inf:
            self.hdlmodule.add_interface(inf.if_name, inf)

    def _add_single_port_interface(self, signal):
        inf = create_single_port_interface(signal)
        if inf:
            self.hdlmodule.add_interface(inf.if_name, inf)
        if signal.is_adaptered():
            self._add_fifo_channel(signal.adapter_sig)
            if signal.is_input():
                item = single_input_port_fifo_adapter(self.hdlmodule, signal)
            else:
                item = single_output_port_fifo_adapter(self.hdlmodule, signal)
            self.hdlmodule.add_decl('', item)

    def _add_internal_fifo(self, signal):
        if signal.is_fifo_port():
            fifo_module = FIFOModule(signal)
        else:
            assert False
        self._add_submodule_instances(fifo_module,
                                      [signal.name],
                                      fifo_module.param_map,
                                      is_internal=True)

    def _add_single_port_channel(self, signal):
        reader, writer = create_local_accessor(signal)
        self.hdlmodule.add_local_reader(reader.acc_name, reader)
        self.hdlmodule.add_local_writer(writer.acc_name, writer)
        ports = reader.regs() + writer.regs()
        for p in ports:
            name = reader.port_name(p)
            sig = self.hdlmodule.gen_sig(name, p.width)
            self.hdlmodule.add_internal_reg(sig)

    def _add_fifo_channel(self, signal):
        reader, writer = create_local_accessor(signal)
        self.hdlmodule.add_local_reader(reader.acc_name, reader)
        self.hdlmodule.add_local_writer(writer.acc_name, writer)
        self._add_internal_fifo(signal)
        ports = reader.ports + writer.ports
        for p in ports:
            name = reader.port_name(p)
            sig = self.hdlmodule.gen_sig(name, p.width)
            if p.dir == 'in':
                self.hdlmodule.add_internal_reg(sig)
            else:
                self.hdlmodule.add_internal_net(sig)

    def _add_reset_stms(self, fsm, defs, uses, outputs):
        fsm_name = fsm.name
        for acc in self.hdlmodule.accessors.values():
            if acc.inf.signal and acc.inf.signal.is_adaptered():
                continue
            for stm in acc.reset_stms():
                self.hdlmodule.add_fsm_reset_stm(fsm_name, stm)
        # reset output ports
        for sig in outputs:
            infs = [inf for inf in self.hdlmodule.interfaces.values() if inf.signal is sig]
            for inf in infs:
                for stm in inf.reset_stms():
                    self.hdlmodule.add_fsm_reset_stm(fsm_name, stm)
        # reset local ports
        for sig in uses:
            if sig.is_seq_port() or sig.is_single_port():
                local_accessors = self.hdlmodule.local_readers.values()
                accs = [acc for acc in local_accessors if acc.inf.signal is sig]
                for acc in accs:
                    for stm in acc.reset_stms():
                        self.hdlmodule.add_fsm_reset_stm(fsm_name, stm)
        for sig in defs:
            # reset internal ports
            if sig.is_seq_port() or sig.is_single_port():
                local_accessors = self.hdlmodule.local_writers.values()
                accs = [acc for acc in local_accessors if acc.inf.signal is sig]
                for acc in accs:
                    for stm in acc.reset_stms():
                        self.hdlmodule.add_fsm_reset_stm(fsm_name, stm)
            # reset internal regs
            elif sig.is_reg():
                if sig.is_initializable():
                    v = AHDL_CONST(sig.init_value)
                else:
                    v = AHDL_CONST(0)
                mv = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), v)
                self.hdlmodule.add_fsm_reset_stm(fsm_name, mv)
        local_readers = self.hdlmodule.local_readers.values()
        local_writers = self.hdlmodule.local_writers.values()
        accs = set(list(local_readers) + list(local_writers))
        for acc in accs:
            # reset local (SinglePort)RAM ports
            if acc.inf.signal.is_memif():
                if acc.inf.signal.sym.scope is fsm.scope:
                    for stm in acc.reset_stms():
                        self.hdlmodule.add_fsm_reset_stm(fsm_name, stm)

    def _add_mem_connections(self, scope):
        mrg = env.memref_graph
        HDLMemPortMaker(mrg.collect_ram(scope), scope, self.hdlmodule).make_port_all()
        for memnode in mrg.collect_immutable(scope):
            if memnode.is_writable():
                HDLTuplePortMaker(memnode, scope, self.hdlmodule).make_port()
        for memnode in mrg.collect_ram(scope):
            if memnode.can_be_reg():
                HDLRegArrayPortMaker(memnode, scope, self.hdlmodule).make_port()


class HDLFunctionModuleBuilder(HDLModuleBuilder):
    def _build_module(self):
        assert len(self.hdlmodule.fsms) == 1
        fsm = self.hdlmodule.fsms[self.hdlmodule.name]
        scope = fsm.scope
        self._add_state_constants(fsm)
        defs, uses, outputs, memnodes = self._collect_vars(fsm)
        locals = defs.union(uses)
        module_name = self.hdlmodule.name
        self._add_state_register(fsm)
        callif = CallInterface('', module_name)
        self.hdlmodule.add_interface('', callif)
        self._add_input_interfaces(scope)
        self._add_output_interfaces(scope)
        self._add_internal_ports(locals)
        self._add_mem_connections(scope)
        self._add_submodules(scope)
        self._add_roms(memnodes)
        self._add_reset_stms(fsm, defs, uses, outputs)

    def _add_input_interfaces(self, scope):
        if scope.is_method():
            assert False
            params = scope.params[1:]
        else:
            params = scope.params
        for i, (sym, copy, _) in enumerate(params):
            if sym.typ.is_int() or sym.typ.is_bool():
                sig_name = '{}_{}'.format(scope.orig_name, sym.hdl_name())
                sig = self.hdlmodule.signal(sig_name)
                inf = SingleReadInterface(sig, sym.hdl_name(), scope.orig_name)
            elif sym.typ.is_list():
                memnode = sym.typ.get_memnode()
                if memnode.can_be_reg():
                    sig = self.hdlmodule.gen_sig(memnode.name(), memnode.data_width(), sym=memnode.sym)
                    inf = RegArrayReadInterface(sig, memnode.name(),
                                                self.hdlmodule.name,
                                                memnode.data_width(),
                                                memnode.length)
                    self.hdlmodule.add_interface(inf.if_name, inf)
                    inf = RegArrayWriteInterface(sig, 'out_{}'.format(copy.name),
                                                 self.hdlmodule.name,
                                                 memnode.data_width(),
                                                 memnode.length)
                    self.hdlmodule.add_interface(inf.if_name, inf)
                    continue
                else:
                    sig = self.hdlmodule.gen_sig(memnode.name(), memnode.data_width(), sym=memnode.sym)
                    inf = RAMBridgeInterface(sig, memnode.name(),
                                             self.hdlmodule.name,
                                             memnode.data_width(),
                                             memnode.addr_width())
                    self.hdlmodule.node2if[memnode] = inf
            elif sym.typ.is_tuple():
                memnode = sym.typ.get_memnode()
                inf = TupleInterface(memnode.name(),
                                     self.hdlmodule.name,
                                     memnode.data_width(),
                                     memnode.length)
            else:
                assert False
            self.hdlmodule.add_interface(inf.if_name, inf)

    def _add_output_interfaces(self, scope):
        if scope.return_type.is_scalar():
            sig_name = '{}_out_0'.format(scope.orig_name)
            sig = self.hdlmodule.signal(sig_name)
            inf = SingleWriteInterface(sig, 'out_0', scope.orig_name)
            self.hdlmodule.add_interface(inf.if_name, inf)
        elif scope.return_type.is_seq():
            raise NotImplementedError('return of a suquence type is not implemented')


def accessor2module(acc):
    if isinstance(acc, FIFOWriteAccessor) or isinstance(acc, FIFOReadAccessor):
        return FIFOModule(acc.inf.signal)
    return None


class HDLTestbenchBuilder(HDLModuleBuilder):
    def _build_module(self):
        assert len(self.hdlmodule.fsms) == 1
        fsm = self.hdlmodule.fsms[self.hdlmodule.name]
        scope = fsm.scope
        self._add_state_constants(fsm)
        defs, uses, outputs, memnodes = self._collect_vars(fsm)
        locals = defs.union(uses)
        self._add_state_register(fsm)
        self._add_internal_ports(locals)
        self._add_mem_connections(scope)
        self._add_submodules(scope)
        for sym, cp, _ in scope.params:
            if sym.typ.is_object() and sym.typ.get_scope().is_module():
                mod_scope = sym.typ.get_scope()
                sub_hdlmodule = env.hdlmodule(mod_scope)
                self._add_submodule_instances(sub_hdlmodule, [cp.name], param_map={})

        # FIXME: FIFO should be in the @module class
        for acc in self.hdlmodule.accessors.values():
            acc_mod = accessor2module(acc)
            if acc_mod:
                connections = defaultdict(list)
                for inf in acc_mod.interfaces.values():
                    inf_acc = inf.accessor(acc.inst_name)
                    if isinstance(inf, WriteInterface):
                        connections['ret'].append((inf, inf_acc))
                    else:
                        connections[''].append((inf, inf_acc))
                self.hdlmodule.add_sub_module(inf_acc.acc_name, acc_mod, connections, acc_mod.param_map)

        self._add_roms(memnodes)
        self._add_reset_stms(fsm, defs, uses, outputs)
        edge_detectors = self._collect_special_decls(fsm)
        for sig, old, new in edge_detectors:
            self.hdlmodule.add_edge_detector(sig, old, new)


class HDLTopModuleBuilder(HDLModuleBuilder):
    def _process_io(self, hdlmodule):
        signals = hdlmodule.get_signals()
        #signals = hdlmodule.signals
        for sig in signals.values():
            if sig.is_single_port():
                self._add_single_port_interface(sig)
            elif sig.is_seq_port():
                self._add_seq_interface(sig)

    def _process_connector_port(self, hdlmodule):
        signals = hdlmodule.get_signals()
        #signals = hdlmodule.signals
        for sig in signals.values():
            if sig.is_input() or sig.is_output():
                continue
            if sig.is_single_port():
                self._add_single_port_channel(sig)
            elif sig.is_seq_port():
                self._add_fifo_channel(sig)

    def _process_fsm(self, fsm):
        scope = fsm.scope
        #self._add_state_constants(worker)
        defs, uses, outputs, memnodes = self._collect_vars(fsm)
        locals = defs.union(uses)
        regs, nets = self._add_internal_ports(locals)
        self._add_state_register(fsm)
        self._add_mem_connections(scope)
        self._add_submodules(scope)
        self._add_roms(memnodes)
        self._add_reset_stms(fsm, defs, uses, outputs)
        edge_detectors = self._collect_special_decls(fsm)
        for sig, old, new in edge_detectors:
            self.hdlmodule.add_edge_detector(sig, old, new)

    def _build_module(self):
        assert self.hdlmodule.scope.is_module()
        assert self.hdlmodule.scope.is_class()
        if not self.hdlmodule.scope.is_instantiated():
            return
        self._process_io(self.hdlmodule)
        self._process_connector_port(self.hdlmodule)

        for fsm in self.hdlmodule.fsms.values():
            if fsm.scope.is_ctor():
                # remove ctor fsm and add constant parameter assigns
                for stm in self._collect_module_defs(fsm):
                    if stm.dst.sig.is_field():
                        assign = AHDL_ASSIGN(stm.dst, stm.src)
                        self.hdlmodule.add_static_assignment(assign, '')
                        self.hdlmodule.add_internal_net(stm.dst.sig, '')
                del self.hdlmodule.fsms[fsm.name]
                break
            else:
                self._add_state_constants(fsm)
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
    def __init__(self, hdlmodule, local_defs, local_uses, output_temps, memnodes):
        self.local_defs = local_defs
        self.local_uses = local_uses
        self.output_temps = output_temps
        self.module_constants = [c for c, _ in hdlmodule.state_constants]
        self.memnodes = memnodes

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.ctx & Ctx.STORE:
            self.local_defs.add(ahdl.sig)
        else:
            self.local_uses.add(ahdl.sig)
        self.memnodes.add(ahdl.memnode)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig.is_ctrl() or ahdl.sig.name in self.module_constants:
            pass
        elif ahdl.sig.is_field():
            pass
        elif ahdl.sig.is_input():
            if ahdl.sig.is_seq_port():
                self.output_temps.add(ahdl.sig)
            elif ahdl.sig.is_single_port():
                self.output_temps.add(ahdl.sig)
        elif ahdl.sig.is_output():
            self.output_temps.add(ahdl.sig)
        else:
            if ahdl.sig.is_adaptered():
                if ahdl.ctx & Ctx.STORE:
                    self.local_defs.add(ahdl.sig.adapter_sig)
                else:
                    self.local_uses.add(ahdl.sig.adapter_sig)
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
            for code in ahdl.codes:
                self.visit(code)
