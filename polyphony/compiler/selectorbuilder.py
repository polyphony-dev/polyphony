from collections import defaultdict
from .ir import Ctx
from .ahdl import *
from .hdlinterface import *
from logging import getLogger
logger = getLogger(__name__)


class SelectorBuilder(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.module_info = self.scope.module_info
        self._build_sub_module_selectors()
        self._build_memory_selectors()

    def _build_memory_selectors(self):
        for ic in self.module_info.interconnects:
            if len(ic.ins) == 1 and len(ic.outs) == 1:
                self._to_direct_connect(ic.name, ic.ins[0], ic.outs[0])
            else:
                if len(ic.ins) == 1:
                    self._to_one2n_interconnect(ic.name, ic.ins[0], ic.outs)
                elif len(ic.outs) == 1:
                    self._to_n2one_interconnect(ic.name, ic.ins, ic.outs[0], ic.cs_name)

    def _to_direct_connect(self, name, inif, outif):
        tag = name
        src = {}
        sink = {}
        for p in inif.ports.all():
            port_name = inif.port_name(p)
            src[p.name] = self.scope.gen_sig(port_name, p.width)
        for p in outif.ports.all():
            port_name = outif.port_name(p)
            sink[p.name] = self.scope.gen_sig(port_name, p.width)

        for p in inif.ports.all():
            port_name = p.name
            if p.dir == 'in':
                lhs = AHDL_VAR(src[port_name], Ctx.STORE)
                rhs = AHDL_VAR(sink[port_name], Ctx.LOAD)
            else:
                lhs = AHDL_VAR(sink[port_name], Ctx.STORE)
                rhs = AHDL_VAR(src[port_name], Ctx.LOAD)
            assign = AHDL_ASSIGN(lhs, rhs)
            self.module_info.add_static_assignment(assign, tag)

    def _to_one2n_interconnect(self, name, inif, outifs):
        tag = name
        trunk = {}
        branches = defaultdict(list)
        for p in inif.ports.all():
            port_name = inif.port_name(p)
            o2n_in_sig = self.scope.gen_sig(port_name, p.width)
            trunk[p.name] = o2n_in_sig
        for oif in outifs:
            for p in oif.ports.all():
                port_name = oif.port_name(p)
                o2n_out_sig = self.scope.gen_sig(port_name, p.width)
                branches[p.name].append(o2n_out_sig)

        #assign switch = {req0, req1, ...}
        switch = self.scope.gen_sig(name + '_switch', len(outifs), ['onehot'])
        switch_var = AHDL_VAR(switch, Ctx.STORE)
        self.module_info.add_internal_net(switch, tag)

        bits = [AHDL_VAR(req, Ctx.LOAD) for req in branches['req']]
        bits.reverse()
        assert len(bits)
        request_bits = AHDL_CONCAT(bits)
        assign = AHDL_ASSIGN(switch_var, request_bits)
        self.module_info.add_static_assignment(assign, tag)

        switch_var = AHDL_VAR(switch, Ctx.LOAD)
        # make interconnect
        for p in inif.ports.all():
            port_name = p.name
            if port_name == 'req':
                reqs = [AHDL_VAR(req, Ctx.LOAD) for req in branches['req']]
                req_ors = AHDL_OP('Or', *reqs)
                assign = AHDL_ASSIGN(AHDL_VAR(trunk[port_name], Ctx.STORE), req_ors)
                self.module_info.add_static_assignment(assign, tag)

            elif port_name == 'len':
                for len_sig in branches['len']:
                    len_var = AHDL_VAR(len_sig, Ctx.LOAD)
                    assign = AHDL_ASSIGN(len_var, AHDL_VAR(trunk[port_name], Ctx.STORE))
                    self.module_info.add_static_assignment(assign, tag)

            else:
                if p.dir == 'in':
                    selector = AHDL_MUX('{}_{}_selector'.format(name, port_name),
                                        switch_var,
                                        branches[port_name],
                                        trunk[port_name])
                    self.module_info.add_mux(selector, tag)

                else:
                    selector = AHDL_DEMUX('{}_{}_selector'.format(name, port_name),
                                          switch_var,
                                          trunk[port_name],
                                          branches[port_name])
                    self.module_info.add_demux(selector, tag)

    def _to_n2one_interconnect(self, name, inifs, outif, cs_name):
        tag = name
        trunk = {}
        branches = defaultdict(list)
        for p in outif.ports.all():
            trunk[p.name] = self.scope.gen_sig(outif.acc_name + '_' + p.name, p.width)
        for iif in inifs:
            for p in iif.ports.all():
                n2o_in_sig = self.scope.gen_sig(iif.acc_name + '_' + p.name, p.width)
                branches[p.name].append(n2o_in_sig)

        # assign switch = cs
        switch = self.scope.gen_sig(name + '_switch', len(inifs), ['onehot'])
        switch_var = AHDL_VAR(switch, Ctx.STORE)
        self.module_info.add_internal_net(switch, tag)

        cs_width = len(inifs)
        cs_sig = self.scope.gen_sig('{}_cs'.format(cs_name), cs_width)
        self.module_info.add_internal_reg(cs_sig, tag)

        cs_var = AHDL_VAR(cs_sig, Ctx.LOAD)
        assign = AHDL_ASSIGN(switch_var, cs_var)
        self.module_info.add_static_assignment(assign, tag)

        switch_var = AHDL_VAR(switch, Ctx.LOAD)
        # make interconnect
        for p in outif.ports.all():
            port_name = p.name
            if p.dir == 'in':
                selector = AHDL_DEMUX('{}_{}_selector'.format(name, port_name),
                                      switch_var,
                                      trunk[port_name],
                                      branches[port_name])
                self.module_info.add_demux(selector, tag)
            else:
                selector = AHDL_MUX('{}_{}_selector'.format(name, port_name),
                                    switch_var,
                                    branches[port_name],
                                    trunk[port_name])
                self.module_info.add_mux(selector, tag)

    def _add_sub_module_accessors(self, connections):
        for inf, acc in connections:
            tag = inf.if_name
            for p in acc.regs():
                int_name = acc.port_name(p)
                sig = self.scope.gen_sig(int_name, p.width)
                self.module_info.add_internal_reg(sig, tag)
            for p in acc.nets():
                int_name = acc.port_name(p)
                sig = self.scope.gen_sig(int_name, p.width)
                self.module_info.add_internal_net(sig, tag)

    def _build_sub_module_selectors(self):
        for name, info, connections, param_map in self.module_info.sub_modules.values():
            # TODO
            if info.name == 'fifo':
                continue
            if connections:
                self._add_sub_module_accessors(connections)
                continue
            if False:  # env.hdl_debug_mode and not self.scope.is_testbench():
                self.emit('always @(posedge clk) begin')
                self.emit('if (rst==0 && {}!={}) begin'.format(self.current_state_sig.name, 0))
                for a in accessors:
                    for p in a.ports.all():
                        aname = a.port_name(p)
                        self.emit('$display("%8d:ACCESSOR :{}      {} = 0x%2h (%1d)", $time, {}, {});'.format(self.scope.orig_name, aname, aname, aname))
                self.emit('end')
                self.emit('end')
                self.emit('')
