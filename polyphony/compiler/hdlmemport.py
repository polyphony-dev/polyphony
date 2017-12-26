from collections import defaultdict, OrderedDict
from .hdlmodule import RAMModule
from .env import env
from .ir import Ctx
from .ahdl import *
from .hdlinterface import *
from .memref import *
from logging import getLogger
logger = getLogger(__name__)


class HDLMemPortMaker(object):
    def __init__(self, memnodes, scope, hdlmodule):
        self.memnodes = memnodes
        self.scope = scope
        self.hdlmodule = hdlmodule
        self.mrg = env.memref_graph
        self.mrg.node2acc = {}
        self.joint_count = 0

    def make_port_all(self):
        memnodes = sorted(self.memnodes)
        for memnode in memnodes:
            self.memnode = memnode
            self.name = memnode.name()
            self.length = memnode.length
            self.width  = memnode.data_width()
            self.addr_width = memnode.addr_width()
            if self.memnode.can_be_reg():
                continue
            self._make_port()

    def _make_ram_accessor(self, node):
        def gen_name():
            self.joint_count += 1
            return 'joint' + str(self.joint_count)
        if node in self.mrg.node2acc:
            return self.mrg.node2acc[node]
        if isinstance(node, tuple):
            memnode = node[0]
            name = gen_name()
            is_sink = False
        else:
            memnode = node
            name = node.name()
            is_sink = True
        sig = self.hdlmodule.gen_sig(name, memnode.data_width())
        acc = RAMAccessor(sig, memnode.data_width(), memnode.addr_width(), is_sink)
        self.mrg.node2acc[node] = acc
        return acc

    def _make_ram_param_accessor(self, inst_name, memnode):
        sig = self.hdlmodule.gen_sig(memnode.name(), memnode.data_width(), sym=memnode.sym)
        ramif = RAMBridgeInterface(sig, memnode.name(), '', memnode.data_width(), memnode.addr_width())
        acc = ramif.accessor(inst_name)
        return acc

    def _add_internal_regs_and_nets(self, ramacc):
        for p in ramacc.regs():
            port_name = ramacc.port_name(p)
            sig = self.hdlmodule.gen_sig(port_name, p.width)
            self.hdlmodule.add_internal_reg(sig, ramacc.acc_name)
            self.hdlmodule.add_fsm_output(self.scope.orig_name, sig)
        for p in ramacc.nets():
            port_name = ramacc.port_name(p)
            sig = self.hdlmodule.gen_sig(port_name, p.width)
            self.hdlmodule.add_internal_net(sig, ramacc.acc_name)

    def _add_internal_nets(self, ramacc):
        for p in ramacc.nets():
            sig = self.hdlmodule.gen_sig(ramacc.acc_name + '_' + p.name, p.width)
            self.hdlmodule.add_internal_net(sig, ramacc.acc_name)

    def _add_ram_module(self):
        param_map = OrderedDict()
        param_map['DATA_WIDTH'] = self.width
        param_map['ADDR_WIDTH'] = self.addr_width
        param_map['RAM_LENGTH'] = self.length
        spram = RAMModule(self.name, self.width, self.addr_width)
        connections = defaultdict(list)
        connections[''] = [(spram.ramif, spram.ramif.accessor(self.name))]
        self.hdlmodule.add_sub_module(self.name, spram, connections, param_map=param_map)
        return spram

    def _add_interconnect(self, name, pred_ifs, succ_ifs):
        #print('add interconnect ', name)
        #print('----pred_ifs')
        #print(pred_ifs)
        #print('----succ_ifs')
        #print(succ_ifs)
        interconnect = Interconnect(name, pred_ifs, succ_ifs)
        self.hdlmodule.add_interconnect(interconnect)

    def _make_port(self):
        assert self.memnode.is_writable()
        # this function makes the node connection for to the successor node
        if isinstance(self.memnode, MemRefNode) or isinstance(self.memnode, MemParamNode):
            if self.memnode.is_source():
                self._make_source_node_connection()
            elif self.memnode.is_param():
                self._make_param_node_connection()
            elif self.memnode.is_sink():
                # add the ram access register and net
                acc = self._make_ram_accessor(self.memnode)
                self._add_internal_regs_and_nets(acc)
                self.hdlmodule.add_local_reader(acc.acc_name, acc)
                self.hdlmodule.add_local_writer(acc.acc_name, acc)
            else:
                assert False
        elif isinstance(self.memnode, N2OneMemNode):
            self._make_n2one_node_connection()
        elif isinstance(self.memnode, One2NMemNode):
            self._make_one2n_node_connection()

    def _make_source_node_connection(self):
        spram = self._add_ram_module()
        spram_acc = spram.ramif.accessor(self.memnode.name())
        assert self.memnode not in self.mrg.node2acc
        self.mrg.node2acc[self.memnode] = spram_acc

        # direct connect
        if isinstance(self.memnode.succs[0], MemRefNode):
            assert len(self.memnode.succs) == 1
            succ = self.memnode.succs[0]
            assert succ.is_sink()
            succ_ramacc = self._make_ram_accessor(succ)
            self._add_interconnect(self.memnode.name(), [spram_acc], [succ_ramacc])

    def _make_param_node_connection(self):
        assert self.memnode in self.hdlmodule.node2if
        assert len(self.memnode.succs) == 1
        succ = self.memnode.succs[0]
        ramif = self.hdlmodule.node2if[self.memnode]
        # direct connect
        if isinstance(succ, MemRefNode):
            ramacc = ramif.accessor()
            assert ramacc not in self.mrg.node2acc
            self.mrg.node2acc[self.memnode] = ramacc
            assert succ.is_sink()
            succ_ramacc = self._make_ram_accessor(succ)
            self._add_interconnect(self.memnode.name(), [ramacc], [succ_ramacc])
        elif isinstance(succ, (One2NMemNode, N2OneMemNode)):
            ramacc = ramif.accessor()
            assert ramacc not in self.mrg.node2acc
            self.mrg.node2acc[self.memnode] = ramacc
            # do not make succ_ramacc here
        else:
            assert False

    def _make_one2n_node_connection(self):
        assert len(self.memnode.preds) == 1
        assert len(self.memnode.succs) > 1

        pred = self.memnode.preds[0]
        if pred.is_source() or isinstance(pred, MemParamNode):
            pred_ramacc = self._make_ram_accessor(pred)
        else:
            pred_ramacc = self._make_ram_accessor((pred, self.memnode))

        succ_ramaccs = []
        for i, succ in enumerate(self.memnode.succs):
            if isinstance(succ, MemParamNode):
                for inst in self.mrg.param_node_instances[succ]:
                    ramacc = self._make_ram_param_accessor(inst, succ)
                    succ_ramaccs.append(ramacc)
            elif isinstance(succ, N2OneMemNode):
                ramacc = self._make_ram_accessor((self.memnode, succ))
                succ_ramaccs.append(ramacc)
                self._add_internal_nets(ramacc)
            elif isinstance(succ, One2NMemNode):
                assert False
            else:
                ramacc = self._make_ram_accessor(succ)
                succ_ramaccs.append(ramacc)
        self._add_interconnect(self.memnode.name(), [pred_ramacc], succ_ramaccs)

    def _make_n2one_node_connection(self):
        assert len(self.memnode.preds) > 1
        assert len(self.memnode.succs) == 1
        succ = self.memnode.succs[0]

        if isinstance(succ, MemParamNode):
            for inst in self.mrg.param_node_instances[succ]:
                pred_ramaccs = []
                preds = [p for p in self.memnode.preds if self.scope is p.scope]
                for i, pred in enumerate(self.memnode.preds):
                    if pred not in preds:
                        continue
                    if isinstance(pred, One2NMemNode):
                        ramacc = self._make_ram_accessor((pred, self.memnode))
                        pred_ramaccs.append(ramacc)
                    else:
                        assert False
                succ_ramacc = self._make_ram_param_accessor(inst, succ)
                self._add_interconnect(succ_ramacc.acc_name, pred_ramaccs, [succ_ramacc])

        else:
            pred_ramaccs = []
            for i, pred in enumerate(self.memnode.preds):
                if isinstance(pred, One2NMemNode):
                    ramacc = self._make_ram_accessor((pred, self.memnode))
                    pred_ramaccs.append(ramacc)
                elif isinstance(pred, MemParamNode):
                    ramacc = self._make_ram_accessor(pred)
                    pred_ramaccs.append(ramacc)
                else:
                    assert False

            if isinstance(succ, MemParamNode):
                assert False
            elif isinstance(succ, JointNode):
                succ_ramacc = self._make_ram_accessor((self.memnode, succ))
                self._add_internal_nets(succ_ramacc)
            else:
                succ_ramacc = self._make_ram_accessor(succ)
            self._add_interconnect(succ_ramacc.acc_name,
                                   pred_ramaccs,
                                   [succ_ramacc]
                                   )


class HDLTuplePortMaker(object):
    def __init__(self, memnode, scope, hdlmodule):
        self.memnode = memnode
        self.name = memnode.name()
        self.scope = scope
        self.mrg = env.memref_graph
        self.hdlmodule = hdlmodule
        self.length = memnode.length
        self.width  = memnode.data_width()

    def make_port(self):
        assert self.memnode.is_writable()
        assert self.memnode.is_immutable()
        # this function makes the node connection for to the successor node
        if isinstance(self.memnode, MemRefNode) or isinstance(self.memnode, MemParamNode):
            if self.memnode.is_source():
                self._make_source_node_connection()
            elif self.memnode.is_param():
                self._make_param_node_connection()
            elif self.memnode.is_sink():
                pass
            else:
                assert False
        elif isinstance(self.memnode, N2OneMemNode):
            pass
        elif isinstance(self.memnode, One2NMemNode):
            self._make_one2n_node_connection()

    def _make_source_node_connection(self):
        sig = self.hdlmodule.gen_sig(self.name, self.width)
        self.hdlmodule.add_internal_reg_array(sig, self.length)
        # direct connect
        if isinstance(self.memnode.succs[0], MemRefNode):
            assert len(self.memnode.succs) == 1
            succ = self.memnode.succs[0]
            assert succ.is_sink()

            src_sig = sig
            ref_sig = self.hdlmodule.gen_sig(succ.name(), succ.data_width())
            self.hdlmodule.add_internal_net_array(ref_sig, succ.length)
            src_mem = AHDL_MEMVAR(src_sig, self.memnode, Ctx.LOAD)
            ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
            for i in range(self.length):
                ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)),
                                          AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                self.hdlmodule.add_static_assignment(ahdl_assign)

    def _make_param_node_connection(self):
        for sink in self.memnode.sinks():
            ref_sig = self.hdlmodule.gen_sig(sink.name(), sink.data_width())
            self.hdlmodule.add_internal_net_array(ref_sig, self.memnode.length)
            ref_mem = AHDL_MEMVAR(ref_sig, sink, Ctx.LOAD)
            for i in range(self.memnode.length):
                sig_name = '{}_{}{}'.format(
                    self.hdlmodule.name,
                    self.memnode.name(),
                    i
                )
                src_sig = self.hdlmodule.gen_sig(sig_name, self.memnode.data_width())
                src_var = AHDL_VAR(src_sig, Ctx.LOAD)
                ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)), src_var)
                self.hdlmodule.add_static_assignment(ahdl_assign)

    def _make_one2n_node_connection(self):
        assert len(self.memnode.preds) == 1
        assert len(self.memnode.succs) > 1

        pred = self.memnode.preds[0]
        for succ in self.memnode.succs:
            if succ.is_sink():
                src_sig = self.hdlmodule.gen_sig(pred.name(), pred.data_width())
                ref_sig = self.hdlmodule.gen_sig(succ.name(), succ.data_width())
                self.hdlmodule.add_internal_net_array(ref_sig, succ.length)
                src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
                for i in range(self.length):
                    ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)),
                                              AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                    self.hdlmodule.add_static_assignment(ahdl_assign)
            elif isinstance(succ, MemParamNode):
                for inst in self.mrg.param_node_instances[succ]:
                    src_sig = self.hdlmodule.gen_sig(pred.name(), pred.data_width())
                    src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                    for i in range(self.length):
                        sig_name = '{}_{}{}'.format(inst, succ.name(), i)
                        ref_sig = self.hdlmodule.gen_sig(sig_name, succ.data_width())
                        ref_var = AHDL_VAR(ref_sig, Ctx.LOAD)
                        ahdl_assign = AHDL_ASSIGN(ref_var, AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                        self.hdlmodule.add_static_assignment(ahdl_assign)


class HDLRegArrayPortMaker(object):
    def __init__(self, memnode, scope, hdlmodule):
        self.memnode = memnode
        self.name = memnode.name()
        self.scope = scope
        self.hdlmodule = env.hdlmodule(scope)
        self.mrg = env.memref_graph
        self.hdlmodule = hdlmodule
        self.length = memnode.length
        self.width  = memnode.data_width()

    def make_port(self):
        assert self.memnode.is_writable()
        #assert self.memnode.is_immutable()
        # this function makes the node connection for to the successor node
        if isinstance(self.memnode, MemRefNode) or isinstance(self.memnode, MemParamNode):
            if self.memnode.is_source():
                self._make_source_node_connection()
            elif self.memnode.is_param():
                self._make_param_node_connection()
            elif self.memnode.is_sink():
                pass
            else:
                assert False
        elif isinstance(self.memnode, N2OneMemNode):
            self._make_n2one_node_connection()
        elif isinstance(self.memnode, One2NMemNode):
            self._make_one2n_node_connection()

    def _make_source_node_connection(self):
        sig = self.hdlmodule.gen_sig(self.name, self.width)
        self.hdlmodule.add_internal_reg_array(sig, self.length)
        return
        # direct connect
        if isinstance(self.memnode.succs[0], MemRefNode):
            assert len(self.memnode.succs) == 1
            succ = self.memnode.succs[0]
            assert succ.is_sink()

            src_sig = sig
            ref_sig = self.hdlmodule.gen_sig(succ.name(), succ.data_width())
            self.hdlmodule.add_internal_reg_array(ref_sig, succ.length)
            src_mem = AHDL_MEMVAR(src_sig, self.memnode, Ctx.LOAD)
            ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
            for i in range(self.length):
                ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)),
                                          AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                self.hdlmodule.add_static_assignment(ahdl_assign)

    def _make_param_node_connection(self):
        for sink in self.memnode.sinks():
            ref_sig = self.hdlmodule.gen_sig(sink.name(), sink.data_width())
            self.hdlmodule.add_internal_reg_array(ref_sig, self.memnode.length)
            ref_mem = AHDL_MEMVAR(ref_sig, sink, Ctx.LOAD)
            for i in range(self.memnode.length):
                sig_name = '{}_out_{}{}'.format(
                    self.hdlmodule.name,
                    self.memnode.name()[len('in_'):],
                    i
                )
                dst_sig = self.hdlmodule.gen_sig(sig_name, self.memnode.data_width())
                dst_var = AHDL_VAR(dst_sig, Ctx.LOAD)
                ahdl_assign = AHDL_ASSIGN(dst_var, AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)))
                self.hdlmodule.add_static_assignment(ahdl_assign)

    def _make_ram_accessor(self, inst_name, memnode):
        ramif = RegArrayAccessor(memnode.name(), '', memnode.data_width(), memnode.addr_width())
        acc = ramif.accessor(inst_name)
        return acc

    def _make_n2one_node_connection(self):
        assert len(self.memnode.preds) > 1
        assert len(self.memnode.succs) == 1
        succ = self.memnode.succs[0]

        callee_name = succ.scope.orig_name
        if isinstance(succ, MemParamNode):
            for inst in self.mrg.param_node_instances[succ]:
                pred_ramaccs = []
                preds = [p for p in self.memnode.preds if self.scope is p.scope]
                for i, pred in enumerate(self.memnode.preds):
                    if pred not in preds:
                        continue
                    if isinstance(pred, One2NMemNode):
                        assert len(pred.preds) == 1
                        src = pred.preds[0]
                        src_sig = self.hdlmodule.gen_sig(src.name(), src.data_width(), sym=src.sym)
                        acc = RegArrayInterface(src_sig, src.name(),
                                                self.hdlmodule.name,
                                                src.data_width(),
                                                src.length, '', True).accessor()
                        acc.ports.ports = acc.ports.flipped()
                        pred_ramaccs.append(acc)
                    else:
                        assert False
                succ_sig = self.hdlmodule.gen_sig(succ.name(), succ.data_width(), sym=succ.sym)
                succ_ramacc = RegArrayInterface(succ_sig, succ.name(),
                                                callee_name,
                                                succ.data_width(),
                                                succ.length, 'in', False).accessor(inst)
                succ_ramacc.ports.ports = succ_ramacc.ports.flipped()
                self._add_interconnect(succ_ramacc.acc_name,
                                       pred_ramaccs,
                                       [succ_ramacc],
                                       )
        elif isinstance(succ, MemRefNode):
            ref_sig = self.hdlmodule.gen_sig(succ.name(), succ.data_width())
            self.hdlmodule.add_internal_reg_array(ref_sig, self.memnode.length)
            ref_len_sig = self.hdlmodule.gen_sig('{}_len'.format(succ.name()), succ.addr_width())
            self.hdlmodule.add_internal_reg(ref_len_sig)

    def _add_interconnect(self, name, pred_ifs, succ_ifs):
        interconnect = Interconnect(name, pred_ifs, succ_ifs)
        self.hdlmodule.add_interconnect(interconnect)

    def _make_one2n_node_connection(self):
        assert len(self.memnode.preds) == 1
        assert len(self.memnode.succs) > 1
        pred = self.memnode.preds[0]
        for succ in self.memnode.succs:
            if succ.is_sink():
                if isinstance(pred, MemParamNode):
                    ref_len_sig = self.hdlmodule.gen_sig('{}_len'.format(succ.name()), succ.addr_width())
                    self.hdlmodule.add_internal_net(ref_len_sig)
                    ahdl_assign = AHDL_ASSIGN(AHDL_VAR(ref_len_sig, Ctx.STORE),
                                              AHDL_CONST(self.length))
                    self.hdlmodule.add_static_assignment(ahdl_assign)
                elif not isinstance(pred, N2OneMemNode):
                    src_sig = self.hdlmodule.gen_sig(pred.name(), pred.data_width())
                    ref_sig = self.hdlmodule.gen_sig(succ.name(), succ.data_width())
                    self.hdlmodule.add_internal_net_array(ref_sig, succ.length)
                    src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                    ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
                    for i in range(self.length):
                        ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)),
                                                  AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                        self.hdlmodule.add_static_assignment(ahdl_assign)
                    ref_len_sig = self.hdlmodule.gen_sig('{}_len'.format(succ.name()), succ.addr_width())
                    self.hdlmodule.add_internal_net(ref_len_sig)
                    ahdl_assign = AHDL_ASSIGN(AHDL_VAR(ref_len_sig, Ctx.STORE),
                                              AHDL_CONST(self.length))
                    self.hdlmodule.add_static_assignment(ahdl_assign)
                else:
                    ref_sig = self.hdlmodule.gen_sig(succ.name(), succ.data_width())
                    self.hdlmodule.add_internal_reg_array(ref_sig, succ.length)
                    ref_len_sig = self.hdlmodule.gen_sig('{}_len'.format(succ.name()), succ.addr_width())
                    self.hdlmodule.add_internal_reg(ref_len_sig)
            elif isinstance(succ, MemParamNode):
                for inst in self.mrg.param_node_instances[succ]:
                    src_sig = self.hdlmodule.gen_sig(pred.name(), pred.data_width())
                    src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                    for i in range(self.length):
                        sig_name = '{}_{}{}'.format(inst, succ.name(), i)
                        ref_sig = self.hdlmodule.gen_sig(sig_name, succ.data_width())
                        ref_var = AHDL_VAR(ref_sig, Ctx.LOAD)
                        ahdl_assign = AHDL_ASSIGN(ref_var, AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                        self.hdlmodule.add_static_assignment(ahdl_assign)
