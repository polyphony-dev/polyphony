from collections import defaultdict
from .ir import Ctx
from .ahdl import *
from .ahdlvisitor import AHDLCollector
from .hdlinterface import *
from logging import getLogger
logger = getLogger(__name__)


class SelectorBuilder(object):
    def __init__(self):
        pass

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        self._build_memory_selectors()

    def _build_memory_selectors(self):
        for ic in self.hdlmodule.interconnects:
            if len(ic.ins) == 1 and len(ic.outs) == 1:
                self._to_direct_connect(ic.name, ic.ins[0], ic.outs[0])
            else:
                if len(ic.ins) == 1:
                    self._to_one2n_interconnect(ic.name, ic.ins[0], ic.outs)
                elif len(ic.outs) == 1:
                    self._to_n2one_interconnect(ic.name, ic.ins, ic.outs[0])
        #self._convert_mem_switch_to_mem_mux()

    def _to_direct_connect(self, name, inif, outif):
        tag = name
        src = {}
        sink = {}
        for p in inif.ports.all():
            port_name = inif.port_name(p)
            src[p.name] = self.hdlmodule.gen_sig(port_name, p.width)
        for p in outif.ports.all():
            port_name = outif.port_name(p)
            sink[p.name] = self.hdlmodule.gen_sig(port_name, p.width)

        for p in inif.ports.all():
            port_name = p.name
            if p.dir == 'in':
                lhs = AHDL_VAR(src[port_name], Ctx.STORE)
                rhs = AHDL_VAR(sink[port_name], Ctx.LOAD)
            else:
                lhs = AHDL_VAR(sink[port_name], Ctx.STORE)
                rhs = AHDL_VAR(src[port_name], Ctx.LOAD)
            assign = AHDL_ASSIGN(lhs, rhs)
            self.hdlmodule.add_static_assignment(assign, tag)

    def _to_one2n_interconnect(self, name, inif, outifs):
        tag = name
        trunk = {}
        branches = defaultdict(list)
        for p in inif.ports.all():
            port_name = inif.port_name(p)
            o2n_in_sig = self.hdlmodule.gen_sig(port_name, p.width)
            trunk[p.name] = o2n_in_sig
        for oif in outifs:
            for p in oif.ports.all():
                port_name = oif.port_name(p)
                o2n_out_sig = self.hdlmodule.gen_sig(port_name, p.width)
                branches[p.name].append(o2n_out_sig)

        #assign switch = {req0, req1, ...}
        switch = self.hdlmodule.gen_sig(name + '_switch', len(outifs), ['onehot'])
        switch_var = AHDL_VAR(switch, Ctx.STORE)
        self.hdlmodule.add_internal_net(switch, tag)

        bits = [AHDL_VAR(req, Ctx.LOAD) for req in branches['req']]
        bits.reverse()
        assert len(bits)
        request_bits = AHDL_CONCAT(bits)
        assign = AHDL_ASSIGN(switch_var, request_bits)
        self.hdlmodule.add_static_assignment(assign, tag)

        switch_var = AHDL_VAR(switch, Ctx.LOAD)
        # make interconnect
        for p in inif.ports.all():
            port_name = p.name
            if port_name == 'req':
                reqs = [AHDL_VAR(req, Ctx.LOAD) for req in branches['req']]
                req_ors = AHDL_OP('Or', *reqs)
                assign = AHDL_ASSIGN(AHDL_VAR(trunk[port_name], Ctx.STORE), req_ors)
                self.hdlmodule.add_static_assignment(assign, tag)

            elif port_name == 'len':
                for len_sig in branches['len']:
                    len_var = AHDL_VAR(len_sig, Ctx.LOAD)
                    assign = AHDL_ASSIGN(len_var, AHDL_VAR(trunk[port_name], Ctx.STORE))
                    self.hdlmodule.add_static_assignment(assign, tag)

            else:
                if p.width == 1:
                    defval = 0
                else:
                    defval = None
                if p.dir == 'in':
                    selector = AHDL_MUX('{}_{}_selector'.format(name, port_name),
                                        switch_var,
                                        branches[port_name],
                                        trunk[port_name],
                                        defval=defval)
                    self.hdlmodule.add_mux(selector, tag)

                else:
                    selector = AHDL_DEMUX('{}_{}_selector'.format(name, port_name),
                                          switch_var,
                                          trunk[port_name],
                                          branches[port_name],
                                          defval=defval)
                    self.hdlmodule.add_demux(selector, tag)

    def _to_n2one_interconnect(self, name, inifs, outif):
        tag = name
        trunk = {}
        branches = defaultdict(list)
        for p in outif.ports.all():
            trunk[p.name] = self.hdlmodule.gen_sig(outif.port_name(p), p.width)
        for iif in inifs:
            for p in iif.ports.all():
                n2o_in_sig = self.hdlmodule.gen_sig(iif.port_name(p), p.width)
                branches[p.name].append(n2o_in_sig)

        # assign switch = cs
        switch = self.hdlmodule.gen_sig(name + '_switch', len(inifs), ['onehot'])
        switch_var = AHDL_VAR(switch, Ctx.STORE)
        self.hdlmodule.add_internal_net(switch, tag)

        assert outif.inf.signal.sym
        assert outif.inf.signal.sym.typ.is_list()
        memnode = outif.inf.signal.sym.typ.get_memnode()
        cs_width = len(inifs)
        if memnode.is_switch():
            cs_sig = self.hdlmodule.gen_sig('{}_cs'.format(name), cs_width, {'reg'})
            self.hdlmodule.add_internal_reg(cs_sig, tag)
            mv = AHDL_MOVE(AHDL_VAR(cs_sig, Ctx.STORE), AHDL_SYMBOL("{}'b0".format(cs_width)))
            if self.hdlmodule is env.hdlmodule(memnode.scope):
                fsm_name = memnode.scope.orig_name
            else:
                fsm_name = memnode.pred_branch().preds[0].scope.orig_name
            self.hdlmodule.add_fsm_reset_stm(fsm_name, mv)
        else:
            cs_sig = self.hdlmodule.gen_sig('{}_cs'.format(name), cs_width, {'net'})
            self.hdlmodule.add_internal_net(cs_sig, tag)

        cs_var = AHDL_VAR(cs_sig, Ctx.LOAD)
        assign = AHDL_ASSIGN(switch_var, cs_var)
        self.hdlmodule.add_static_assignment(assign, tag)

        switch_var = AHDL_VAR(switch, Ctx.LOAD)
        # make interconnect
        for p in outif.ports.all():
            port_name = p.name
            if p.width == 1:
                defval = 0
            else:
                defval = None
            if p.dir == 'in':
                selector = AHDL_DEMUX('{}_{}_selector'.format(name, port_name),
                                      switch_var,
                                      trunk[port_name],
                                      branches[port_name],
                                      defval=defval)
                self.hdlmodule.add_demux(selector, tag)
            else:
                selector = AHDL_MUX('{}_{}_selector'.format(name, port_name),
                                    switch_var,
                                    branches[port_name],
                                    trunk[port_name],
                                    defval=defval)
                self.hdlmodule.add_mux(selector, tag)

    def _convert_mem_switch_to_mem_mux(self):
        collector = AHDLCollector(AHDL_META)
        collector.process(self.hdlmodule)
        switches = defaultdict(list)
        for state, codes in collector.results.items():
            for ahdl in codes:
                if ahdl.metaid == 'MEM_SWITCH':
                    dst_node = ahdl.args[1]
                    src_node = ahdl.args[2]
                    switches[dst_node].append((state, src_node, ahdl))
        for dst_node, srcs in switches.items():
            dst_sig = self.hdlmodule.gen_sig(dst_node.name(), dst_node.data_width(), {'memif'}, dst_node.sym)
            dst_var = AHDL_MEMVAR(dst_sig, dst_node, Ctx.STORE)
            src_vars = []
            conds = []
            for state, src_node, memsw in srcs:
                fsm = state.stg.fsm
                state_var = AHDL_VAR(fsm.state_var, Ctx.LOAD)
                cond = AHDL_OP('Eq', state_var, AHDL_SYMBOL(state.name))
                src_sig = self.hdlmodule.gen_sig(src_node.name(), src_node.data_width(), {'memif'}, src_node.sym)
                src_var = AHDL_MEMVAR(src_sig, src_node, Ctx.LOAD)
                conds.append(cond)
                src_vars.append(src_var)
                self._remove_code(state, memsw)
            memmux = AHDL_META('MEM_MUX', memsw.args[0], dst_var, src_vars, conds)
            state.codes.insert(0, memmux)

    def _remove_code(self, state, code):
        if code in state.codes:
            state.codes.remove(code)
            return True
        for c in state.codes:
            if hasattr(c, 'codes'):
                if self._remove_code(c, code):
                    return True
            elif hasattr(c, 'blocks'):
                for blk in c.blocks:
                    if self._remove_code(c, code):
                        return True
        return False
