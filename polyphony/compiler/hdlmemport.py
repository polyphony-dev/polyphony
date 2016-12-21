from collections import OrderedDict, namedtuple, defaultdict
from .hdlmoduleinfo import HDLModuleInfo, RAMModuleInfo
from .env import env
from .ir import Ctx
from .ahdl import *
from .hdlinterface import *
from .memref import *
from logging import getLogger, DEBUG
logger = getLogger(__name__)
import pdb


class HDLMemPortMaker:
    def __init__(self, memnode, scope, module_info):
        self.memnode = memnode
        #if memnode.object_sym:
        #    self.name = '{}_{}'.format(memnode.object_sym.hdl_name(), memnode.sym.ancestor.hdl_name())
        #else:
        self.name = memnode.name()
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = module_info
        self.length = memnode.length
        self.width  = memnode.width
        self.addr_width = memnode.addr_width()

    def _make_ram_if(self, name, thru=False, is_public=False):
        ramif = RAMInterface(name, self.width, self.addr_width, thru=thru, is_public=is_public)
        return ramif

    def _make_ram_access_if(self, name, thru=False):
        ramif = RAMAccessInterface(name, self.width, self.addr_width, thru=thru)
        return ramif

    def _add_internal_regs_and_nets(self, ramif):
        for p in ramif.ports:
            sig = self.scope.gen_sig(ramif.name+'_'+p.basename, p.width)
            if p.dir == 'in':
                self.module_info.add_internal_reg(sig, ramif.name)
                self.module_info.add_fsm_output(self.scope.name, sig)
            else:
                self.module_info.add_internal_net(sig, ramif.name)

    def _add_internal_nets(self, ramif):
        for p in ramif.ports:
            sig = self.scope.gen_sig(ramif.name+'_'+p.basename, p.width)
            self.module_info.add_internal_net(sig, ramif.name)

    def _add_ram_module(self):
        param_map = OrderedDict()
        #TODO: bit length
        param_map['DATA_WIDTH'] = self.width
        param_map['ADDR_WIDTH'] = self.addr_width
        param_map['RAM_LENGTH'] = self.length

        shared = True if self.memnode.succ_ref_nodes() else False
        spram_info = RAMModuleInfo(self.name, self.width, self.addr_width)
        if shared:
            ram_accessor = self._make_ram_if('', thru=True, is_public=True) 
            accessors = [ram_accessor]
            self.module_info.add_sub_module(self.name, spram_info, accessors, param_map=param_map)
        else:
            accessors = [spram_info.ramif]
            self.module_info.add_sub_module(self.name, spram_info, accessors, param_map=param_map)
        self.module_info.node2if[self.memnode] = spram_info.ramif

    def _add_interconnect(self, name, pred_ifs, succ_ifs, cs_name=''):
        #print('add interconnect ', name)
        #print('----pred_ifs')
        #print(pred_ifs)
        #print('----succ_ifs')
        #print(succ_ifs)
        if cs_name:
            self.module_info.add_interconnect(Interconnect(name, pred_ifs, succ_ifs, cs_name=cs_name))
        else:
            self.module_info.add_interconnect(Interconnect(name, pred_ifs, succ_ifs))

    def make_port(self):
        assert self.memnode.is_writable()
        # this function makes the node connection for to the successor node
        if isinstance(self.memnode, MemRefNode) or isinstance(self.memnode, MemParamNode):
            if self.memnode.is_source():
                self._make_source_node_connection()
            elif self.memnode.is_param():
                self._make_param_node_connection()
            elif self.memnode.is_sink():
                # add the ram access register and net
                self._add_internal_regs_and_nets(self._make_ram_access_if(self.memnode.name()))
            else:
                assert False
        elif isinstance(self.memnode, N2OneMemNode):
            self._make_n2one_node_connection()
        elif isinstance(self.memnode, One2NMemNode):
            self._make_one2n_node_connection()

    def _make_source_node_connection(self):
        self._add_ram_module()
        ramif = self._make_ram_if(self.memnode.name())

        # direct connect
        if isinstance(self.memnode.succs[0], MemRefNode):
            assert len(self.memnode.succs) == 1
            succ = self.memnode.succs[0]
            assert succ.is_sink()
            succ_ramif = self._make_ram_access_if(succ.name())
            self._add_interconnect(self.memnode.name(), [ramif], [succ_ramif])

    def _make_param_node_connection(self):
        # TODO from/to external access
        ramif = RAMAccessInterface(self.name, self.width, self.addr_width, flip=True, thru=True)
        self.module_info.add_interface(ramif)
        self.module_info.node2if[self.memnode] = ramif

        # direct connect
        if isinstance(self.memnode.succs[0], MemRefNode):
            # specify the module name explicitly
            ramif = self._make_ram_access_if(self.module_info.name + '_' + self.name)
            assert len(self.memnode.succs) == 1
            succ = self.memnode.succs[0]
            assert succ.is_sink()
            succ_ramif = self._make_ram_access_if(succ.name())
            self._add_interconnect(self.memnode.name(), [ramif], [succ_ramif])

    def _make_one2n_node_connection(self):
        assert len(self.memnode.preds) == 1
        assert len(self.memnode.succs) > 1

        pred = self.memnode.preds[0]
        if pred.is_source():
            pred_ramif = self._make_ram_if(pred.name())
        else:
            if isinstance(pred, One2NMemNode):
                #i = pred.succs.index(self.memnode)
                name = '{}_in'.format(self.memnode.name())
            elif isinstance(pred, N2OneMemNode):
                name = '{}_out'.format(pred.name())
            elif pred.is_param():
                name = self.module_info.name + '_' + pred.name()
            else:
                name = pred.name()
            pred_ramif = self._make_ram_access_if(name)

        succ_ramifs = []
        for i, succ in enumerate(self.memnode.succs):
            if isinstance(succ, MemParamNode):
                for inst in self.mrg.param_node_instances[succ]:
                    ramif = self._make_ram_access_if(inst + '_' + succ.name())
                    succ_ramifs.append(ramif)
            elif isinstance(succ, N2OneMemNode):
                if isinstance(succ.succs[0], MemParamNode):
                    for inst in self.mrg.param_node_instances[succ.succs[0]]:
                        name = '{}_{}_in{}'.format(inst, succ.name(), succ.preds.index(self.memnode))
                        ramif = self._make_ram_access_if(name)
                        succ_ramifs.append(ramif)
                        # add the intermediate nets for connection to the successor node
                        self._add_internal_nets(ramif)
                else:
                    name = '{}_in{}'.format(succ.name(), succ.preds.index(self.memnode))
                    ramif = self._make_ram_access_if(name)
                    succ_ramifs.append(ramif)
                    # add the intermediate nets for connection to the successor node
                    self._add_internal_nets(ramif)
            elif isinstance(succ, One2NMemNode):
                name = '{}_in'.format(succ.name())
                ramif = self._make_ram_access_if(name)
                succ_ramifs.append(ramif)
                # add the intermediate nets for connection to the successor node
                self._add_internal_nets(ramif)
                #assert False
            else:
                ramif = self._make_ram_access_if(succ.name())
                succ_ramifs.append(ramif)
        self._add_interconnect(self.memnode.name(), [pred_ramif], succ_ramifs)

    def _make_n2one_node_connection(self):
        assert len(self.memnode.preds) > 1
        assert len(self.memnode.succs) == 1
        succ = self.memnode.succs[0]

        if isinstance(succ, MemParamNode):
            for inst in self.mrg.param_node_instances[succ]:
                pred_ramifs = []
                preds = [p for p in self.memnode.preds if self.scope in p.scopes]
                for i, pred in enumerate(self.memnode.preds):
                    if pred not in preds:
                        continue
                    if isinstance(pred, One2NMemNode):
                        name = '{}_{}_in{}'.format(inst, self.memnode.name(), i)
                        ramif = self._make_ram_access_if(name)
                        pred_ramifs.append(ramif)
                    else:
                        ramif = self._make_ram_access_if(pred.name())
                        pred_ramifs.append(ramif)
                succ_ramif = self._make_ram_access_if(inst + '_' + succ.name())
                cs_name = inst+'_'+self.memnode.orig_succs[0].name()
                self._add_interconnect(succ_ramif.name, pred_ramifs, [succ_ramif], cs_name)

        else:
            pred_ramifs = []
            for i, pred in enumerate(self.memnode.preds):
                if isinstance(pred, MemParamNode):
                    assert 0
                elif isinstance(pred, One2NMemNode):
                    name = '{}_in{}'.format(self.memnode.name(), i)
                    ramif = self._make_ram_access_if(name)
                    pred_ramifs.append(ramif)
                else:
                    assert isinstance(pred, MemRefNode)
                    ramif = self._make_ram_access_if(pred.name())
                    pred_ramifs.append(ramif)

            if isinstance(succ, MemParamNode):
                succ_ramif = self._make_ram_access_if(succ.name())
            elif isinstance(succ, JointNode):
                succ_ramif = self._make_ram_access_if('{}_out'.format(self.memnode.name()))
                # add the intermediate nets for connection to the successor node
                self._add_internal_nets(succ_ramif)
            else:
                succ_ramif = self._make_ram_access_if(succ.name())
            cs_name = self.memnode.orig_succs[0].name()
            self._add_interconnect(succ_ramif.name, pred_ramifs, [succ_ramif], cs_name=cs_name)

class HDLRegArrayPortMaker:
    def __init__(self, memnode, scope, module_info):
        self.memnode = memnode
        self.name = memnode.name()
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = module_info
        self.length = memnode.length
        self.width  = memnode.width

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

            src_sig = self.scope.gen_sig(self.name, self.width)
            ref_sig = self.scope.gen_sig(succ.name(), succ.width)
            self.module_info.add_internal_net_array(ref_sig, succ.length)
            src_mem = AHDL_MEMVAR(src_sig, self.memnode, Ctx.LOAD)
            ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
            for i in range(self.length):
                ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)), AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                self.module_info.add_static_assignment(ahdl_assign)

    def _make_param_node_connection(self):
        for sink in self.memnode.sinks():
            ref_sig = self.scope.gen_sig(sink.name(), sink.width)
            self.module_info.add_internal_net_array(ref_sig, self.memnode.length)
            ref_mem = AHDL_MEMVAR(ref_sig, sink, Ctx.LOAD)
            for i in range(self.memnode.length):
                src_sig = self.scope.gen_sig('{}_{}{}'.format(self.module_info.name, self.memnode.name(), i), self.memnode.width)
                src_var = AHDL_VAR(src_sig, Ctx.LOAD)
                ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)), src_var)
                self.module_info.add_static_assignment(ahdl_assign)
        regarrayif = RegArrayInterface(self.memnode.name(), self.memnode.width, self.memnode.length)
        self.module_info.add_interface(regarrayif)

    def _make_one2n_node_connection(self):
        assert len(self.memnode.preds) == 1
        assert len(self.memnode.succs) > 1

        pred = self.memnode.preds[0]
        for succ in self.memnode.succs:
            if succ.is_sink():
                src_sig = self.scope.gen_sig(pred.name(), pred.width)
                ref_sig = self.scope.gen_sig(succ.name(), succ.width)
                self.module_info.add_internal_net_array(ref_sig, succ.length)
                src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                ref_mem = AHDL_MEMVAR(ref_sig, succ, Ctx.LOAD)
                for i in range(self.length):
                    ahdl_assign = AHDL_ASSIGN(AHDL_SUBSCRIPT(ref_mem, AHDL_CONST(i)), AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                    self.module_info.add_static_assignment(ahdl_assign)
            elif isinstance(succ, MemParamNode):
                for inst in self.mrg.param_node_instances[succ]:
                    src_sig = self.scope.gen_sig(pred.name(), pred.width)
                    src_mem = AHDL_MEMVAR(src_sig, pred, Ctx.LOAD)
                    for i in range(self.length):
                        ref_sig = self.scope.gen_sig('{}_{}{}'.format(inst, succ.name(), i), succ.width)
                        ref_var = AHDL_VAR(ref_sig, Ctx.LOAD)
                        ahdl_assign = AHDL_ASSIGN(ref_var, AHDL_SUBSCRIPT(src_mem, AHDL_CONST(i)))
                        self.module_info.add_static_assignment(ahdl_assign)
