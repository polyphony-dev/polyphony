from collections import OrderedDict, namedtuple, defaultdict
from .hdlmoduleinfo import HDLModuleInfo
from .env import env
from .common import INT_WIDTH
from .ir import Ctx
from .ahdl import *
from . import libs
from logging import getLogger, DEBUG
logger = getLogger(__name__)
import pdb


class HDLMemPortMaker:
    @classmethod
    def create(cls, memnode, scope, module_info):
        if memnode.is_source():
            if memnode.succs:
                return RootMemPortMaker(memnode, scope, module_info)
            else:
                return DirectMemPortMaker(memnode, scope, module_info)
        else:
            if all([memnode.scope is not pred.scope for pred in memnode.preds]):
                if memnode.succs:
                    return BranchMemPortMaker(memnode, scope, module_info)
                else:
                    return LeafMemPortMaker(memnode, scope, module_info)
            else:
                return JunctionMaker(memnode, scope, module_info)

    def __init__(self, memnode, scope, module_info):
        self.memnode = memnode
        if memnode.object_sym:
            self.name = '{}_{}'.format(memnode.object_sym.hdl_name(), memnode.sym.ancestor.hdl_name())
        else:
            self.name = memnode.sym.hdl_name()
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = module_info
        self.length, self.width, self.addr_width = HDLMemPortMaker.get_safe_sizes(self.mrg, memnode)

    @classmethod
    def make_port_map(cls, scope, module_info, callee_instance, callee_memnode, caller_memnodes, port_map):
        if callee_memnode.is_writable():
            cls.make_ram_port_map(scope, module_info, callee_instance, callee_memnode, caller_memnodes, port_map)


    @classmethod
    def make_ram_port_map(cls, scope, module_info, callee_instance, callee_memnode, caller_memnodes, port_map):
        names = [str(callee_memnode.param_index)]
        names.extend([memnode.sym.hdl_name() for memnode in caller_memnodes])
        name = '_'.join(names)
        src_name = callee_instance + '_' + name
        dst_name = callee_memnode.sym.hdl_name()
        if callee_memnode.succs:
            #is branch memport
            br_postfix = '_br'
        else:
            br_postfix = ''
        _, port_data_width, port_addr_width = cls.get_safe_sizes(env.memref_graph, callee_memnode)
        ports = [
            ('q',    port_data_width, ['wire', 'int']),
            ('len',  port_addr_width, ['wire']),
            ('d',    port_data_width, ['wire', 'int']),
            ('addr', port_addr_width, ['wire']),
            ('we',   1,               ['wire']),
            ('req',  1,               ['wire'])
        ]
        for postfix, _, _ in ports:
            port_map[dst_name + '_' + postfix + br_postfix] =  src_name + '_' + postfix

        cls._add_internals(module_info, scope, src_name, ports)
        if len(caller_memnodes) <= 1:
            return

        branch_names = []
        for memnode in caller_memnodes:
            each_caller_name = '{}_{}_{}'.format(callee_instance, callee_memnode.param_index, memnode.sym.hdl_name())
            branch_names.append(each_caller_name)
            cls._add_internals(module_info, scope, 
                               each_caller_name,
                               ports)
            csname = each_caller_name + '_cs'
            cssig = scope.gen_sig(csname, 1)
            module_info.add_internal_reg(cssig)

        signals = [
            ('addr', port_addr_width),
            ('d',    port_data_width),
            ('q',    port_data_width),
            ('len',  port_addr_width),
            ('we',   1),
            ('req',  1),
            ('cs',   1)
        ]

        trunk = {}
        for postfix, width in signals:
            sig = scope.gen_sig(src_name + '_' + postfix, width)
            trunk[postfix] = sig

        branches = defaultdict(list)
        for branch in branch_names:
            for postfix, width in signals:
                sig = scope.gen_sig(branch + '_' + postfix, width)
                if sig not in branches[postfix]:
                    branches[postfix].append(sig)
            
        #assign selector = {req0, req1, ...}
        sel = scope.gen_sig(src_name + '_select_sig', len(branches['cs']))
        selector_var = AHDL_VAR(sel, Ctx.STORE)
        chipselect_bits = AHDL_CONCAT(reversed([AHDL_VAR(cs, Ctx.LOAD) for cs in branches['cs']]))
        module_info.add_static_assignment(AHDL_ASSIGN(selector_var, chipselect_bits))
        module_info.add_internal_wire(sel)

        selector_var = AHDL_VAR(sel, Ctx.LOAD)
        # make demux for input ports
        demux = AHDL_DEMUX(src_name + '_addr_selector', selector_var, trunk['addr'], branches['addr'])
        module_info.add_demux(demux)

        demux = AHDL_DEMUX(src_name + '_d_selector', selector_var, trunk['d'], branches['d'])
        module_info.add_demux(demux)

        demux = AHDL_DEMUX(src_name + '_we_selector', selector_var, trunk['we'], branches['we'])
        module_info.add_demux(demux)

        demux = AHDL_DEMUX(src_name + '_req_selector', selector_var, trunk['req'], branches['req'])
        module_info.add_demux(demux)

        # make mux for output port
        mux = AHDL_MUX(src_name + '_q_selector', selector_var, branches['q'], trunk['q'])
        module_info.add_mux(mux)

        mux = AHDL_MUX(src_name + '_len_selector', selector_var, branches['len'], trunk['len'])
        module_info.add_mux(mux)

    @classmethod
    def get_safe_sizes(cls, mrg, memnode):
        memroot = mrg.get_single_root(memnode)
        if memroot:
            return memroot.length, memroot.width, memroot.length.bit_length()+1
        else:
            return -1, 32, 13

    @classmethod
    def _add_internals(cls, module_info, scope, prefix, ports):
        for postfix, width, attr in ports:
            name = prefix + '_' + postfix
            sig = scope.gen_sig(name, width, attr)
            if sig.is_wire():
                module_info.add_internal_wire(sig)
            else:
                module_info.add_internal_reg(sig)

    def _add_mem_ports(self, mem_ports):
        for postfix, width, attr in mem_ports:
            sig = self.scope.gen_sig(self.name + '_' + postfix, width, attr)
            if sig.is_input():
                self.module_info.add_mem_input(sig)
            else:
                self.module_info.add_mem_output(sig)



class DirectMemPortMaker(HDLMemPortMaker):
    '''non shared memory connection'''
    def __init__(self, memnode, scope, module_info):
        super().__init__(memnode, scope, module_info)

    def make_hdl(self):
        self._make_ram_module()
        self._make_access_ports()

    def _make_ram_module(self):
        width = INT_WIDTH
        addr_width = self.addr_width

        port_map = OrderedDict()
        port_map['D'] = self.name + '_d'
        port_map['Q'] = self.name + '_q'
        port_map['ADDR'] = self.name + '_addr'
        port_map['WE'] = self.name + '_we'
        port_map['LEN'] = self.name + '_len'

        param_map = OrderedDict()
        #TODO: bit length
        param_map['DATA_WIDTH'] = width
        param_map['ADDR_WIDTH'] = addr_width
        param_map['RAM_LENGTH'] = self.length

        spram_info = HDLModuleInfo('BidirectionalSinglePortRam', '@top'+'.BidirectionalSinglePortRam')
        self.module_info.add_sub_module(self.name, spram_info, port_map, param_map)
        env.add_using_lib(libs.bidirectional_single_port_ram)

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #internal ports
        ports = [
            ('q',    width,      ['wire', 'int']),
            ('len',  addr_width, ['wire']),
            ('d',    width,      ['reg', 'int']),
            ('addr', addr_width, ['reg']),
            ('we',   1,          ['reg']),
            ('req',  1,          ['reg'])
        ]
        self._add_internals(self.module_info, self.scope, self.name, ports)


class RootMemPortMaker(HDLMemPortMaker):
    def __init__(self, memnode, scope, module_info):
        super().__init__(memnode, scope, module_info)

    def make_hdl(self):
        self._make_ram_module()
        self._make_access_ports()
        self._make_connection()

    def _make_ram_module(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #internal ports
        ports = [
            ('q_ram',    width,      ['wire', 'int']),
            ('len_ram',  addr_width, ['wire']),
            ('d_ram',    width,      ['wire', 'int']),
            ('addr_ram', addr_width, ['wire']),
            ('we_ram',   1,          ['wire'])
        ]
        self._add_internals(self.module_info, self.scope, self.name, ports)

        port_map = OrderedDict()
        port_map['D'] = self.name + '_d_ram'
        port_map['Q'] = self.name + '_q_ram'
        port_map['ADDR'] = self.name + '_addr_ram'
        port_map['WE'] = self.name + '_we_ram'
        port_map['LEN'] = self.name + '_len_ram'

        param_map = OrderedDict()
        #TODO: bit length
        param_map['DATA_WIDTH'] = width
        param_map['ADDR_WIDTH'] = addr_width
        param_map['RAM_LENGTH'] = self.length

        spram_info = HDLModuleInfo('BidirectionalSinglePortRam', '@top' +'.BidirectionalSinglePortRam')
        self.module_info.add_sub_module(self.name, spram_info, port_map, param_map)
        env.add_using_lib(libs.bidirectional_single_port_ram)

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #internal ports
        ports = [
            ('q',    width,      ['wire', 'int']),
            ('len',  addr_width, ['wire']),
            ('d',    width,      ['reg', 'int']),
            ('addr', addr_width, ['reg']),
            ('we',   1,          ['reg']),
            ('req',  1,          ['reg'])
        ]
        self._add_internals(self.module_info, self.scope, self.name, ports)

    def _make_connection(self):
        addr_width = self.addr_width
        data_width = INT_WIDTH #TODO

        src_prefix = self.name

        signals = [
            ('addr', addr_width),
            ('d', data_width),
            ('q', data_width),
            ('len', addr_width),
            ('we', 1),
            ('req', 1)
        ]

        trunk = {}
        for postfix, width in signals:
            trunk[postfix] = self.scope.gen_sig(src_prefix + '_' + postfix + '_ram', width)

        branches = defaultdict(list)
        for postfix, width in signals:
            sig = self.scope.gen_sig(src_prefix + '_' + postfix, width)
            assert sig not in branches[postfix]
            branches[postfix].append(sig)

        for inst, succ in self.mrg.collect_inst_succs(self.memnode):
            dst_prefix = '{}_{}_{}'.format(inst, succ.param_index, self.name)
            for postfix, width in signals:
                sig = self.scope.gen_sig(dst_prefix + '_' + postfix, width)
                assert sig not in branches[postfix]
                branches[postfix].append(sig)

        # add reference nodes in this scope
        for succ in sorted(self.memnode.succs):
            if succ.scope is self.memnode.scope:
                dst_prefix = '{}_{}'.format(self.name, succ.sym.hdl_name())
                for postfix, width in signals:
                    sig = self.scope.gen_sig(dst_prefix + '_' + postfix, width)
                    assert sig not in branches[postfix]
                    branches[postfix].append(sig)

        #assign selector = {req0, req1, ...}                
        sel = self.scope.gen_sig(src_prefix + '_select_sig_ram', len(branches['req']))
        selector_var = AHDL_VAR(sel, Ctx.STORE)
        request_bits = AHDL_CONCAT(reversed([AHDL_VAR(req, Ctx.LOAD) for req in branches['req']]))
        self.module_info.add_static_assignment(AHDL_ASSIGN(selector_var, request_bits))
        self.module_info.add_internal_wire(sel)

        selector_var = AHDL_VAR(sel, Ctx.LOAD)
        # make mux for input ports
        mux = AHDL_MUX(src_prefix + '_addr_selector_ram', selector_var, branches['addr'], trunk['addr'])
        self.module_info.add_mux(mux)

        mux = AHDL_MUX(src_prefix + '_d_selector_ram', selector_var, branches['d'], trunk['d'])
        self.module_info.add_mux(mux)
        
        mux = AHDL_MUX(src_prefix + '_we_selector_ram', selector_var, branches['we'], trunk['we'])
        self.module_info.add_mux(mux)

        # make demux for output port
        demux = AHDL_DEMUX(src_prefix + '_q_selector_ram', selector_var, trunk['q'], branches['q'])
        self.module_info.add_demux(demux)

        for branch_len in branches['len']:
            self.module_info.add_static_assignment(AHDL_ASSIGN(AHDL_VAR(branch_len, Ctx.STORE), AHDL_VAR(trunk['len'], Ctx.LOAD)))


class BranchMemPortMaker(HDLMemPortMaker):
    def __init__(self, memnode, scope, module_info):
        super().__init__(memnode, scope, module_info)

    def make_hdl(self):
        self._make_access_ports()
        self._make_connection()

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        mem_ports = [
            ('q_br',    width,      ['in', 'wire']),
            ('len_br',  addr_width, ['in', 'wire']),
            ('req_br',  1,          ['out', 'wire']),
            ('d_br',    width,      ['out', 'wire']),
            ('addr_br', addr_width, ['out', 'wire']),
            ('we_br',   1,          ['out', 'wire'])
        ]
        self._add_mem_ports(mem_ports)

        #internal ports
        ports = [
            ('q',    width,        ['wire', 'int']),
            ('len',  addr_width-1, ['wire']),
            ('d',    width,        ['reg', 'int']),
            ('addr', addr_width,   ['reg']),
            ('we',   1,            ['reg']),
            ('req',  1,            ['reg'])
        ]
        self._add_internals(self.module_info, self.scope, self.name, ports)

    def _make_connection(self):
        addr_width = self.addr_width
        data_width = INT_WIDTH #TODO

        src_prefix = self.name

        signals = [
            ('addr', addr_width),
            ('d', data_width),
            ('q', data_width),
            ('len', addr_width),
            ('we', 1),
            ('req', 1)
        ]

        trunk = {}
        for postfix, width in signals:
            trunk[postfix] = self.scope.gen_sig(src_prefix + '_' + postfix + '_br', width)

        branches = defaultdict(list)
        for postfix, width in signals:
            sig = self.scope.gen_sig(src_prefix + '_' + postfix, width)
            assert sig not in branches[postfix]
            branches[postfix].append(sig)

        for inst, succ in self.mrg.collect_inst_succs(self.memnode):
            dst_prefix = '{}_{}_{}'.format(inst, succ.param_index, self.name)
            for postfix, width in signals:
                sig = self.scope.gen_sig(dst_prefix + '_' + postfix, width)
                assert sig not in branches[postfix]
                branches[postfix].append(sig)

        # add reference nodes in this scope
        for succ in sorted(self.memnode.succs):
            if succ.scope is self.memnode.scope:
                dst_prefix = '{}_{}'.format(self.name, succ.sym.hdl_name())
                for postfix, width in signals:
                    sig = self.scope.gen_sig(dst_prefix + '_' + postfix, width)
                    assert sig not in branches[postfix]
                    branches[postfix].append(sig)

        #assign selector = {req0, req1, ...}                
        sel = self.scope.gen_sig(src_prefix + '_select_sig_br', len(branches['req']))
        selector_var = AHDL_VAR(sel, Ctx.STORE)
        request_bits = AHDL_CONCAT(reversed([AHDL_VAR(req, Ctx.LOAD) for req in branches['req']]))
        self.module_info.add_static_assignment(AHDL_ASSIGN(selector_var, request_bits))
        self.module_info.add_internal_wire(sel)

        req_out = self.scope.gen_sig(self.name + '_req_br', len(branches['req']))
        req_out_var = AHDL_VAR(req_out, Ctx.STORE)
        
        req_ors = AHDL_VAR(branches['req'][0], Ctx.LOAD)
        for req in branches['req'][1:]:
            req_ors = AHDL_OP('Or', req_ors, AHDL_VAR(req, Ctx.LOAD))
        self.module_info.add_static_assignment(AHDL_ASSIGN(req_out_var, req_ors))

        selector_var = AHDL_VAR(sel, Ctx.LOAD)
        # make mux for input ports
        mux = AHDL_MUX(src_prefix + '_addr_selector_br', selector_var, branches['addr'], trunk['addr'])
        self.module_info.add_mux(mux)

        mux = AHDL_MUX(src_prefix + '_d_selector_br', selector_var, branches['d'], trunk['d'])
        self.module_info.add_mux(mux)
        
        mux = AHDL_MUX(src_prefix + '_we_selector_br', selector_var, branches['we'], trunk['we'])
        self.module_info.add_mux(mux)

        # make demux for output port
        demux = AHDL_DEMUX(src_prefix + '_q_selector_br', selector_var, trunk['q'], branches['q'])
        self.module_info.add_demux(demux)

        for branch_len in branches['len']:
            self.module_info.add_static_assignment(AHDL_ASSIGN(AHDL_VAR(branch_len, Ctx.STORE), AHDL_VAR(trunk['len'], Ctx.LOAD)))

class LeafMemPortMaker(HDLMemPortMaker):
    def __init__(self, memnode, scope, module_info):
        super().__init__(memnode, scope, module_info)

    def make_hdl(self):
        self._make_access_ports()

    def _make_access_ports(self):
        if self.memnode.object_sym:
            ports = [
                ('q',    self.width,      ['wire', 'int']),
                ('len',  self.addr_width, ['wire']),
                ('req',  1,               ['reg']),
                ('d',    self.width,      ['reg', 'int']),
                ('addr', self.addr_width, ['reg']),
                ('we',   1,               ['reg'])
            ]
            self._add_internals(self.module_info, self.scope, self.name, ports)
        else:
            mem_ports = [
                ('q',    self.width,      ['in', 'wire']),
                ('len',  self.addr_width, ['in', 'wire']),
                ('req',  1,               ['out', 'reg']),
                ('d',    self.width,      ['out', 'reg']),
                ('addr', self.addr_width, ['out', 'reg']),
                ('we',   1,               ['out', 'reg'])
            ]
            self._add_mem_ports(mem_ports)


class JunctionMaker(HDLMemPortMaker):
    def __init__(self, memnode, scope, module_info):
        super().__init__(memnode, scope, module_info)

    def make_hdl(self):
        self._make_access_ports()
        self._make_connection()

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width

        #internal ports
        # for direct access
        ports = [
            ('q',    width,        ['wire', 'int']),
            ('len',  addr_width-1, ['wire']),
            ('d',    width,        ['reg', 'int']),
            ('addr', addr_width,   ['reg']),
            ('we',   1,            ['reg']),
            ('req',  1,            ['reg'])
        ]
        self._add_internals(self.module_info, self.scope, self.name, ports)

        # for indirect access to predesessor nodes
        for pred in self.memnode.preds:
            prefix = '{}_{}'.format(pred.sym.hdl_name(), self.name)
            ports = [
                ('q',    width,        ['wire', 'int']),
                ('len',  addr_width-1, ['wire']),
                ('d',    width,        ['wire', 'int']),
                ('addr', addr_width,   ['wire']),
                ('we',   1,            ['wire']),
                ('req',  1,            ['wire'])
            ]
            self._add_internals(self.module_info, self.scope, prefix, ports)

        # bridge
        ports = [
            ('bridge_q',    width,        ['wire', 'int']),
            ('bridge_len',  addr_width-1, ['wire']),
            ('bridge_d',    width,        ['wire', 'int']),
            ('bridge_addr', addr_width,   ['wire']),
            ('bridge_we',   1,            ['wire']),
            ('bridge_req',  1,            ['wire'])
        ]
        self._add_internals(self.module_info, self.scope, self.name, ports)

    def _make_connection(self):
        addr_width = self.addr_width
        data_width = INT_WIDTH #TODO

        signals = [
            ('addr', addr_width),
            ('d', data_width),
            ('q', data_width),
            ('len', addr_width),
            ('we', 1),
            ('req', 1)
        ]

        this = {}
        src_prefix = self.name + '_bridge'
        for postfix, width in signals:
            this[postfix] = self.scope.gen_sig(src_prefix + '_' + postfix, width)

        # for accessee
        accessees = defaultdict(list)

        # for indirect access to predesessor nodes
        for pred in sorted(self.memnode.preds):
            if pred.scope is not self.memnode.scope:
                continue
            dst_prefix = '{}_{}'.format(pred.sym.hdl_name(), self.name)
            for postfix, width in signals:
                sig = self.scope.gen_sig(dst_prefix + '_' + postfix, width)
                accessees[postfix].append(sig)

        #assign selector = {req0, req1, ...}                
        sel = self.scope.gen_sig(src_prefix + '_sel', len(accessees['req']))
        self.module_info.add_internal_reg(sel)

        selector_var = AHDL_VAR(sel, Ctx.LOAD)
        # make demux
        demux = AHDL_DEMUX(src_prefix + '_addr_selector', selector_var, this['addr'], accessees['addr'])
        self.module_info.add_demux(demux)

        demux = AHDL_DEMUX(src_prefix + '_d_selector', selector_var, this['d'], accessees['d'])
        self.module_info.add_demux(demux)
        
        demux = AHDL_DEMUX(src_prefix + '_we_selector', selector_var, this['we'], accessees['we'])
        self.module_info.add_demux(demux)

        one = self.scope.gen_sig('1', 1)
        demux = AHDL_DEMUX(src_prefix + '_req_selector', selector_var, one, accessees['req'])
        self.module_info.add_demux(demux)
        
        # make mux
        mux = AHDL_MUX(src_prefix + '_q_selector', selector_var, accessees['q'], this['q'])
        self.module_info.add_mux(mux)

        mux = AHDL_MUX(src_prefix + '_len_selector', selector_var, accessees['len'], this['len'])
        self.module_info.add_mux(mux)

        # for accessor
        accessors = defaultdict(list)

        # for indirect access from sub-module nodes
        for inst, succ in self.mrg.collect_inst_succs(self.memnode):
            dst_prefix = '{}_{}_{}'.format(inst, succ.param_index, self.name)
            for postfix, width in signals:
                sig = self.scope.gen_sig(dst_prefix + '_' + postfix, width)
                assert sig not in accessors[postfix]
                accessors[postfix].append(sig)

        # for indirect access from successor nodes
        for succ in sorted(self.memnode.succs):
            if succ.scope is not self.memnode.scope:
                continue
            dst_prefix = '{}_{}'.format(self.name, succ.sym.hdl_name())
            for postfix, width in signals:
                sig = self.scope.gen_sig(dst_prefix + '_' + postfix, width)
                assert sig not in accessors[postfix]
                accessors[postfix].append(sig)
        # for direct access
        for postfix, width in signals:
            sig = self.scope.gen_sig(self.name+'_' + postfix, width)
            assert sig not in accessors[postfix]
            accessors[postfix].append(sig)

        if accessors:
            #assign selector = {req0, req1, ...}
            sel = self.scope.gen_sig(src_prefix + '_select_sig', len(accessors['req']))
            selector_var = AHDL_VAR(sel, Ctx.STORE)
            request_bits = AHDL_CONCAT(reversed([AHDL_VAR(req, Ctx.LOAD) for req in accessors['req']]))
            self.module_info.add_static_assignment(AHDL_ASSIGN(selector_var, request_bits))
            self.module_info.add_internal_wire(sel)

            selector_var = AHDL_VAR(sel, Ctx.LOAD)
            # make mux for input ports
            mux = AHDL_MUX(src_prefix + '_addr_selector', selector_var, accessors['addr'], this['addr'])
            self.module_info.add_mux(mux)

            mux = AHDL_MUX(src_prefix + '_d_selector', selector_var, accessors['d'], this['d'])
            self.module_info.add_mux(mux)

            mux = AHDL_MUX(src_prefix + '_we_selector', selector_var, accessors['we'], this['we'])
            self.module_info.add_mux(mux)

            # make demux for output port
            demux = AHDL_DEMUX(src_prefix + '_q_selector', selector_var, this['q'], accessors['q'])
            self.module_info.add_demux(demux)

            for branch_len in accessors['len']:
                self.module_info.add_static_assignment(AHDL_ASSIGN(AHDL_VAR(branch_len, Ctx.STORE), AHDL_VAR(this['len'], Ctx.LOAD)))

