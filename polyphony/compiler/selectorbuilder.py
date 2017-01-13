from collections import OrderedDict
from .verilog_common import pyop2verilogop
from .ir import Ctx
from .signal import Signal
from .ahdl import *
from .env import env
from .type import Type
from .hdlinterface import *
from .memref import One2NMemNode, N2OneMemNode
from .utils import unique
from logging import getLogger
logger = getLogger(__name__)


class SelectorBuilder:
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
        for p in inif.ports:
            src[p.basename] = self.scope.gen_sig(inif.name + '_' + p.basename, p.width)
        for p in outif.ports:
            sink[p.basename] = self.scope.gen_sig(outif.name + '_' + p.basename, p.width)

        for p in inif.ports:
            port_name = p.basename
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
        for p in inif.ports:
            o2n_in_sig = self.scope.gen_sig(inif.name + '_' + p.basename, p.width)
            trunk[p.basename] = o2n_in_sig
        for oif in outifs:
            for p in oif.ports:
                o2n_out_sig = self.scope.gen_sig(oif.name + '_' + p.basename, p.width)
                branches[p.basename].append(o2n_out_sig)

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
        for p in inif.ports:
            port_name = p.basename
            if port_name == 'req':
                req_ors = AHDL_VAR(branches['req'][0], Ctx.LOAD)
                for req in branches['req'][1:]:
                    req_ors = AHDL_OP('Or', req_ors, AHDL_VAR(req, Ctx.LOAD))
                assign = AHDL_ASSIGN(AHDL_VAR(trunk[port_name], Ctx.STORE), req_ors)
                self.module_info.add_static_assignment(assign, tag)

            elif port_name == 'len':
                for len_sig in branches['len']:
                    len_var = AHDL_VAR(len_sig, Ctx.LOAD)
                    assign = AHDL_ASSIGN(len_var, AHDL_VAR(trunk[port_name], Ctx.STORE))
                    self.module_info.add_static_assignment(assign, tag)

            else:
                if p.dir == 'in':
                    selector = AHDL_MUX('{}_{}_selector'.format(name, port_name), switch_var, branches[port_name], trunk[port_name])
                    self.module_info.add_mux(selector, tag)

                else:
                    selector = AHDL_DEMUX('{}_{}_selector'.format(name, port_name), switch_var, trunk[port_name], branches[port_name])
                    self.module_info.add_demux(selector, tag)


    def _to_n2one_interconnect(self, name, inifs, outif, cs_name):
        tag = name
        trunk = {}
        branches = defaultdict(list)
        for p in outif.ports:
            trunk[p.basename] = self.scope.gen_sig(outif.name + '_' + p.basename, p.width)
        for iif in inifs:
            for p in iif.ports:
                n2o_in_sig = self.scope.gen_sig(iif.name + '_' + p.basename, p.width)
                branches[p.basename].append(n2o_in_sig)

        # assign switch = cs
        switch = self.scope.gen_sig(name + '_switch', len(inifs), ['onehot'])
        switch_var = AHDL_VAR(switch, Ctx.STORE)
        self.module_info.add_internal_net(switch, tag)

        cs_width = len(inifs)
        #cs_sig = self.scope.gen_sig('{}_cs'.format(outif.name), cs_width)
        cs_sig = self.scope.gen_sig('{}_cs'.format(cs_name), cs_width)
        self.module_info.add_internal_reg(cs_sig, tag)

        cs_var = AHDL_VAR(cs_sig, Ctx.LOAD)
        assign = AHDL_ASSIGN(switch_var, cs_var)
        self.module_info.add_static_assignment(assign, tag)

        switch_var = AHDL_VAR(switch, Ctx.LOAD)
        # make interconnect
        for p in outif.ports:
            port_name = p.basename
            if p.dir == 'in':
                selector = AHDL_DEMUX('{}_{}_selector'.format(name, port_name), switch_var, trunk[port_name], branches[port_name])
                self.module_info.add_demux(selector, tag)
            else:
                selector = AHDL_MUX('{}_{}_selector'.format(name, port_name), switch_var, branches[port_name], trunk[port_name])
                self.module_info.add_mux(selector, tag)

    def _build_sub_module_selectors(self):
        for name, info, accessors, sub_infs, param_map in self.module_info.sub_modules.values():
            infs = []
            for a in accessors:
                if not a.is_public:
                    continue
                infs.extend(sub_infs[a.name])
            infs = unique(infs)
            for inf in infs:
                trunk = {}
                branches = defaultdict(list)
                tag = inf.name

                for p in inf.ports:
                    sig = self.scope.gen_sig(inf.port_name('sub', p), p.width)
                    trunk[p.basename] = sig
                    self.module_info.add_internal_net(sig, tag)

                    if inf.is_public:
                        ext_name = inf.port_name(self.module_info.name, p)
                        sig = self.scope.gen_sig(ext_name, p.width)
                        branches[p.basename].append(sig)

                    int_name = inf.port_name('', p)
                    sig = self.scope.gen_sig(int_name, p.width)
                    branches[p.basename].append(sig)
                    if p.dir=='in' and not inf.thru:
                        self.module_info.add_internal_reg(sig, tag)
                    else:
                        self.module_info.add_internal_net(sig, tag)

                switch_width = 2 if inf.is_public else 1 # TODO
                # make interconnect
                for p in inf.ports:
                    port_name = p.basename
                    if p.dir == 'in':
                        if p.basename == 'ready' or p.basename == 'accept':
                            bits = [AHDL_SYMBOL(sig.name) for sig in branches[p.basename]]
                            bits.reverse()
                            concat = AHDL_CONCAT(bits, 'BitOr')
                            assign = AHDL_ASSIGN(AHDL_VAR(trunk[port_name], Ctx.STORE), concat)
                            self.module_info.add_static_assignment(assign, tag)
                        else:
                            if switch_width > 1:
                                switch = self.scope.gen_sig('sub_' + inf.name + '_switch', switch_width, ['onehot'])
                                switch_var = AHDL_VAR(switch, Ctx.STORE)
                                self.module_info.add_internal_net(switch, tag)

                                bits = [AHDL_SYMBOL(sig.name) for sig in branches['ready']]
                                bits.reverse()
                                ready_bits = AHDL_CONCAT(bits)
                                assign = AHDL_ASSIGN(switch_var, ready_bits)
                                self.module_info.add_static_assignment(assign, tag)

                                switch_var = AHDL_VAR(switch, Ctx.LOAD)
                                selector = AHDL_MUX('{}_{}_selector'.format(inf.name, port_name), switch_var, branches[port_name], trunk[port_name])
                                self.module_info.add_mux(selector, tag)
                            else:
                                assign = AHDL_ASSIGN(AHDL_VAR(trunk[port_name], Ctx.STORE), AHDL_VAR(branches[port_name][0], Ctx.LOAD))
                                self.module_info.add_static_assignment(assign, tag)
                    else:
                        for sig in branches[port_name]:
                            assign = AHDL_ASSIGN(AHDL_VAR(sig, Ctx.STORE), AHDL_VAR(trunk[port_name], Ctx.LOAD))
                            self.module_info.add_static_assignment(assign, tag)
                                
            if False: #env.hdl_debug_mode and not self.scope.is_testbench():
                self.emit('always @(posedge clk) begin')
                self.emit('if (rst==0 && {}!={}) begin'.format(self.current_state_sig.name, 0))
                for a in accessors:
                    for p in a.ports:
                        #aname = self._accessor_name(name, a, p)
                        aname = a.port_name(name, p)
                        self.emit('$display("%8d:ACCESSOR :{}      {} = 0x%2h (%1d)", $time, {}, {});'.format(self.scope.orig_name, aname, aname, aname))
                self.emit('end')
                self.emit('end')
                self.emit('')
