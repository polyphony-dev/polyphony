from collections import OrderedDict
from .hdlmoduleinfo import RAMModuleInfo
from .env import env
from .ir import Ctx
from .ahdl import *
from .hdlinterface import *
from .memref import *
from logging import getLogger
logger = getLogger(__name__)


class HDLMemPortMaker(object):
    def __init__(self, memnodes, scope, module_info):
        self.memnodes = memnodes
        self.scope = scope
        self.module_info = module_info
        self.mrg = env.memref_graph
        self.mrg.node2acc = {}
        self.joint_count = 0

    def make_port_all(self):
        for memnode in sorted(self.memnodes):
            self.memnode = memnode
            self.name = memnode.name()
            self.length = memnode.length
            self.width  = memnode.data_width()
            self.addr_width = memnode.addr_width()
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
        sig = self.scope.gen_sig(name, memnode.data_width())
        acc = RAMAccessor(sig, memnode.data_width(), memnode.addr_width(), is_sink)
        self.mrg.node2acc[node] = acc
        return acc

    def _make_ram_param_accessor(self, inst_name, memnode):
        ramif = RAMBridgeInterface(memnode.name(), '', memnode.data_width(), memnode.addr_width())
        acc = ramif.accessor(inst_name)
        return acc

    def _add_internal_regs_and_nets(self, ramacc):
        for p in ramacc.regs():
            port_name = ramacc.port_name(p)
            sig = self.scope.gen_sig(port_name, p.width)
            self.module_info.add_internal_reg(sig, ramacc.acc_name)
            self.module_info.add_fsm_output(self.scope.orig_name, sig)
        for p in ramacc.nets():
            port_name = ramacc.port_name(p)
            sig = self.scope.gen_sig(port_name, p.width)
            self.module_info.add_internal_net(sig, ramacc.acc_name)

    def _add_internal_nets(self, ramacc):
        for p in ramacc.nets():
            sig = self.scope.gen_sig(ramacc.acc_name + '_' + p.name, p.width)
            self.module_info.add_internal_net(sig, ramacc.acc_name)

    def _add_ram_module(self):
        param_map = OrderedDict()
        param_map['DATA_WIDTH'] = self.width
        param_map['ADDR_WIDTH'] = self.addr_width
        param_map['RAM_LENGTH'] = self.length
        spram_info = RAMModuleInfo(self.name, self.width, self.addr_width)
        connections = [(spram_info.ramif, spram_info.ramif.accessor(self.name))]
        self.module_info.add_sub_module(self.name, spram_info, connections, param_map=param_map)
        return spram_info

    def _add_interconnect(self, name, pred_ifs, succ_ifs, cs_name=''):
        #print('add interconnect ', name)
        #print('----pred_ifs')
        #print(pred_ifs)
        #print('----succ_ifs')
        #print(succ_ifs)
        if cs_name:
            interconnect = Interconnect(name, pred_ifs, succ_ifs, cs_name=cs_name)
        else:
            interconnect = Interconnect(name, pred_ifs, succ_ifs)
        self.module_info.add_interconnect(interconnect)

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
                self.module_info.add_local_reader(acc.acc_name, acc)
                self.module_info.add_local_writer(acc.acc_name, acc)
            else:
                assert False
        elif isinstance(self.memnode, N2OneMemNode):
            self._make_n2one_node_connection()
        elif isinstance(self.memnode, One2NMemNode):
            self._make_one2n_node_connection()

    def _make_source_node_connection(self):
        spram_info = self._add_ram_module()
        spram_acc = spram_info.ramif.accessor(self.memnode.name())
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
        assert self.memnode in self.module_info.node2if
        ramif = self.module_info.node2if[self.memnode]

        # direct connect
        if isinstance(self.memnode.succs[0], MemRefNode):
            ramacc = ramif.accessor()
            assert ramacc not in self.mrg.node2acc
            self.mrg.node2acc[self.memnode] = ramacc

            assert len(self.memnode.succs) == 1
            succ = self.memnode.succs[0]
            assert succ.is_sink()
            succ_ramacc = self._make_ram_accessor(succ)
            self._add_interconnect(self.memnode.name(), [ramacc], [succ_ramacc])

    def _make_one2n_node_connection(self):
        assert len(self.memnode.preds) == 1
        assert len(self.memnode.succs) > 1

        pred = self.memnode.preds[0]
        if pred.is_source():
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
                preds = [p for p in self.memnode.preds if self.scope in p.scopes]
                for i, pred in enumerate(self.memnode.preds):
                    if pred not in preds:
                        continue
                    if isinstance(pred, One2NMemNode):
                        ramacc = self._make_ram_accessor((pred, self.memnode))
                        pred_ramaccs.append(ramacc)
                    else:
                        assert False
                succ_ramacc = self._make_ram_param_accessor(inst, succ)
                cs_name = inst + '_' + self.memnode.orig_succs[0].name()
                self._add_interconnect(succ_ramacc.acc_name, pred_ramaccs, [succ_ramacc], cs_name)

        else:
            pred_ramaccs = []
            for i, pred in enumerate(self.memnode.preds):
                if isinstance(pred, One2NMemNode):
                    ramacc = self._make_ram_accessor((pred, self.memnode))
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
            cs_name = self.memnode.orig_succs[0].name()
            self._add_interconnect(succ_ramacc.acc_name,
                                   pred_ramaccs,
                                   [succ_ramacc],
                                   cs_name=cs_name)


class HDLRegArrayPortMaker(object):
    def __init__(self, memnode, scope, module_info):
        self.memnode = memnode
        self.name = memnode.name()
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = module_info
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
        sig = self.scope.gen_sig(self.name, self.width)
        self.module_info.add_internal_reg_array(sig, self.length)
        # direct connect
        if isinstance(self.memnode.succs[0], MemRefNode):
            assert len(self.memnode.succs) == 1
            succ = self.memnode.succs[0]
            assert succ.is_sink()

            src_sig = sig
            ref_sig = self.scope.gen_sig(succ.name(), succ.data_width())
            self.module_info.add_internal_net_array(ref_sig, succ.length)
            src_mem = AHDL_MEMVAR(src_sig, self.memnode, Ctx.LOAD)
            ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
            for i in range(self.length):
                ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)),
                                          AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                self.module_info.add_static_assignment(ahdl_assign)

    def _make_param_node_connection(self):
        for sink in self.memnode.sinks():
            ref_sig = self.scope.gen_sig(sink.name(), sink.data_width())
            self.module_info.add_internal_net_array(ref_sig, self.memnode.length)
            ref_mem = AHDL_MEMVAR(ref_sig, sink, Ctx.LOAD)
            for i in range(self.memnode.length):
                sig_name = '{}_{}{}'.format(
                    self.module_info.name,
                    self.memnode.name(),
                    i
                )
                src_sig = self.scope.gen_sig(sig_name, self.memnode.data_width())
                src_var = AHDL_VAR(src_sig, Ctx.LOAD)
                ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)), src_var)
                self.module_info.add_static_assignment(ahdl_assign)

    def _make_one2n_node_connection(self):
        assert len(self.memnode.preds) == 1
        assert len(self.memnode.succs) > 1

        pred = self.memnode.preds[0]
        for succ in self.memnode.succs:
            if succ.is_sink():
                src_sig = self.scope.gen_sig(pred.name(), pred.data_width())
                ref_sig = self.scope.gen_sig(succ.name(), succ.data_width())
                self.module_info.add_internal_net_array(ref_sig, succ.length)
                src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
                for i in range(self.length):
                    ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)),
                                              AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                    self.module_info.add_static_assignment(ahdl_assign)
            elif isinstance(succ, MemParamNode):
                for inst in self.mrg.param_node_instances[succ]:
                    src_sig = self.scope.gen_sig(pred.name(), pred.data_width())
                    src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                    for i in range(self.length):
                        sig_name = '{}_{}{}'.format(inst, succ.name(), i)
                        ref_sig = self.scope.gen_sig(sig_name, succ.data_width())
                        ref_var = AHDL_VAR(ref_sig, Ctx.LOAD)
                        ahdl_assign = AHDL_ASSIGN(ref_var, AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                        self.module_info.add_static_assignment(ahdl_assign)
