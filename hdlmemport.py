from collections import OrderedDict, namedtuple, defaultdict
from hdlmoduleinfo import HDLModuleInfo
from env import env
from common import INT_WIDTH
from ahdl import AHDL_CONST, AHDL_VAR, AHDL_CONCAT, AHDL_OP, AHDL_IF_EXP, AHDL_ASSIGN, AHDL_CONNECT, AHDL_FUNCALL, AHDL_FUNCTION, AHDL_CASE, AHDL_CASE_ITEM, AHDL_MUX, AHDL_DEMUX
from logging import getLogger, DEBUG
logger = getLogger(__name__)


Port = namedtuple('Port', ('postfix', 'typ', 'width', 'sign'))
Signal = namedtuple('Signal', ('postfix', 'width'))


class HDLMemPortMaker:
    @classmethod
    def create(cls, meminfo, scope, module_info):
        if meminfo.ref_index < 0:
            if meminfo.shared:
                return RootMemPortMaker(meminfo, scope, module_info)
            else:
                return DirectMemPortMaker(meminfo, scope, module_info)
        else:
            if meminfo.shared:
                return BranchMemPortMaker(meminfo, scope, module_info)
            else:
                return LeafMemPortMaker(meminfo, scope, module_info)

    def __init__(self, meminfo, scope, module_info):
        self.meminfo = meminfo
        self.name = meminfo.sym.hdl_name()
        self.scope = scope
        self.module_info = module_info
        self.addr_width = meminfo.length.bit_length()+1
        assert self.addr_width > 0

    def make_port_map(self, callee_scope, callee_instance, port_map):
        for linked_meminfo in self._collect_linked_meminfo(callee_scope, callee_instance, self.meminfo):
            data_width = INT_WIDTH #TODO: use minfo.width
            addr_width = self.addr_width
            src_name = callee_instance + '_' + self.name
            if linked_meminfo.shared:
                #is branch memport
                dst_name = linked_meminfo.sym.hdl_name() + '_io'
            else:
                #is leaf mem port
                dst_name = linked_meminfo.sym.hdl_name()

            ports = [
                Port('q',    'wire', data_width, 'signed'),
                Port('d',    'wire', data_width, 'signed'),
                Port('addr', 'wire', addr_width, '/*unsigned*/'),
                Port('we',   'wire', 1, 'signed'),
                Port('req',  'wire', 1, 'signed')
            ]
            for port in ports:
                port_map[dst_name + '_' + port.postfix] =  src_name + '_' + port.postfix

            self._add_internals(src_name, ports)
            

    def _collect_linked_meminfo(self, callee_scope, callee_instance, meminfo):
        for linked_inst, linked_meminfo in meminfo.links[callee_scope]:
            if callee_instance == linked_inst:
                yield linked_meminfo
        return None

    def _add_internals(self, prefix, ports):
        for port in ports:
            name = prefix + '_' + port.postfix
            if port.typ == 'wire':
                self.module_info.add_internal_wire(name, port.width, port.sign)
            else:
                self.module_info.add_internal_reg(name, port.width, port.sign)




class DirectMemPortMaker(HDLMemPortMaker):
    '''non shared memory connection'''
    def __init__(self, meminfo, scope, module_info):
        super().__init__(meminfo, scope, module_info)

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

        param_map = OrderedDict()
        #TODO: bit length
        param_map['DATA_WIDTH'] = width
        param_map['ADDR_WIDTH'] = addr_width
        param_map['RAM_LENGTH'] = self.meminfo.length

        spram_info = HDLModuleInfo('BidirectionalSinglePortRam', '@top'+'.BidirectionalSinglePortRam')
        self.module_info.add_sub_module(self.name, spram_info, port_map, param_map)

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #internal ports
        ports = [
            Port('q',    'wire', width, 'signed'),
            Port('d',    'reg', width, 'signed'),
            Port('addr', 'reg', addr_width, '/*unsigned*/'),
            Port('we',   'reg', 1, 'signed'),
            Port('req',  'reg', 1, 'signed')
        ]
        self._add_internals(self.name, ports)


class RootMemPortMaker(HDLMemPortMaker):
    def __init__(self, meminfo, scope, module_info):
        super().__init__(meminfo, scope, module_info)

    def make_hdl(self):
        self._make_ram_module()
        self._make_access_ports()
        self._make_connection()

    def _make_ram_module(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #internal ports
        ports = [
            Port('mux_q',    'wire', width, 'signed'),
            Port('mux_d',    'wire', width, 'signed'),
            Port('mux_addr', 'wire', addr_width, '/*unsigned*/'),
            Port('mux_we',   'wire', 1, 'signed')
        ]
        self._add_internals(self.name, ports)

        port_map = OrderedDict()
        port_map['D'] = self.name + '_mux_d'
        port_map['Q'] = self.name + '_mux_q'
        port_map['ADDR'] = self.name + '_mux_addr'
        port_map['WE'] = self.name + '_mux_we'

        param_map = OrderedDict()
        #TODO: bit length
        param_map['DATA_WIDTH'] = width
        param_map['ADDR_WIDTH'] = addr_width
        param_map['RAM_LENGTH'] = self.meminfo.length

        spram_info = HDLModuleInfo('BidirectionalSinglePortRam', '@top' +'.BidirectionalSinglePortRam')
        self.module_info.add_sub_module(self.name, spram_info, port_map, param_map)

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #internal ports
        ports = [
            Port('q',    'wire', width, 'signed'),
            Port('d',    'reg', width, 'signed'),
            Port('addr', 'reg', addr_width, '/*unsigned*/'),
            Port('we',   'reg', 1, 'signed'),
            Port('req',  'reg', 1, 'signed')
        ]
        self._add_internals(self.name, ports)

    def _make_connection(self):
        addr_width = self.addr_width
        data_width = INT_WIDTH #TODO

        src_prefix = self.name
        mux_prefix = self.name + '_mux'

        signals = [
            Signal('addr', addr_width),
            Signal('d', data_width),
            Signal('q', data_width),
            Signal('we', 1),
            Signal('req', 1)
        ]

        trunk = {}
        for s in signals:
            sym = self.scope.gen_sym(mux_prefix + '_' + s.postfix)
            sym.width = s.width
            trunk[s.postfix] = AHDL_VAR(sym)

        branches = defaultdict(list)
        for s in signals:
            sym = self.scope.gen_sym(src_prefix + '_' + s.postfix)
            sym.width = s.width
            branches[s.postfix].append(AHDL_VAR(sym))

        for memlinks in self.meminfo.links.values():
            for inst, linked_meminfo in memlinks:
                dst_prefix = '{}_{}'.format(inst, self.name)
                for s in signals:
                    sym = self.scope.gen_sym(dst_prefix + '_' + s.postfix)
                    sym.width = s.width
                    branches[s.postfix].append(AHDL_VAR(sym))

        #assign selector = {req0, req1, ...}                
        sel = self.scope.gen_sym(mux_prefix + '_select_sig')
        sel.width = len(branches['req'])
        selector_var = AHDL_VAR(sel)
        request_bits = AHDL_CONCAT(reversed(branches['req']))
        self.module_info.add_static_assignment(AHDL_ASSIGN(selector_var, request_bits))
        self.module_info.add_internal_wire(sel.name, sel.width, '/*unsigned*/')

        # make mux for input ports
        addr_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_addr_selector'))
        mux = AHDL_MUX(addr_selector, selector_var, branches['addr'], trunk['addr'], addr_width)
        self.module_info.add_mux(mux)

        d_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_d_selector'))
        mux = AHDL_MUX(d_selector, selector_var, branches['d'], trunk['d'], INT_WIDTH)
        self.module_info.add_mux(mux)
        
        we_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_we_selector'))
        mux = AHDL_MUX(we_selector, selector_var, branches['we'], trunk['we'], 1)
        self.module_info.add_mux(mux)

        # make demux for output port
        q_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_q_selector'))
        demux = AHDL_DEMUX(q_selector, selector_var, trunk['q'], branches['q'], INT_WIDTH)
        self.module_info.add_demux(demux)


class BranchMemPortMaker(HDLMemPortMaker):
    def __init__(self, meminfo, scope, module_info):
        super().__init__(meminfo, scope, module_info)

    def make_hdl(self):
        self._make_access_ports()
        self._make_connection()

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #input port
        self.module_info.add_input(self.name + '_io_q', 'wire', width)
        #output port
        self.module_info.add_output(self.name + '_io_req', 'wire', 1)
        self.module_info.add_output(self.name + '_io_d', 'wire', width)
        self.module_info.add_output(self.name + '_io_addr', 'wire', addr_width)
        self.module_info.add_output(self.name + '_io_we', 'wire', 1)

        #internal ports
        ports = [
            Port('q',    'wire', width, 'signed'),
            Port('d',    'reg', width, 'signed'),
            Port('addr', 'reg', addr_width, '/*unsigned*/'),
            Port('we',   'reg', 1, 'signed'),
            Port('req',  'reg', 1, 'signed')
        ]
        self._add_internals(self.name, ports)

    def _make_connection(self):
        addr_width = self.addr_width
        data_width = INT_WIDTH #TODO

        src_prefix = self.name
        mux_prefix = self.name + '_io'

        signals = [
            Signal('addr', addr_width),
            Signal('d', data_width),
            Signal('q', data_width),
            Signal('we', 1),
            Signal('req', 1)
        ]

        trunk = {}
        for s in signals:
            sym = self.scope.gen_sym(mux_prefix + '_' + s.postfix)
            sym.width = s.width
            trunk[s.postfix] = AHDL_VAR(sym)

        branches = defaultdict(list)
        for s in signals:
            sym = self.scope.gen_sym(src_prefix + '_' + s.postfix)
            sym.width = s.width
            branches[s.postfix].append(AHDL_VAR(sym))

        for memlinks in self.meminfo.links.values():
            for inst, linked_meminfo in memlinks:
                dst_prefix = '{}_{}'.format(inst, self.name)
                for s in signals:
                    sym = self.scope.gen_sym(dst_prefix + '_' + s.postfix)
                    sym.width = s.width
                    branches[s.postfix].append(AHDL_VAR(sym))

        #assign selector = {req0, req1, ...}                
        sel = self.scope.gen_sym(mux_prefix + '_select_sig')
        sel.width = len(branches['req'])
        selector_var = AHDL_VAR(sel)
        request_bits = AHDL_CONCAT(reversed(branches['req']))
        self.module_info.add_static_assignment(AHDL_ASSIGN(selector_var, request_bits))
        self.module_info.add_internal_wire(sel.name, sel.width, '/*unsigned*/')

        req_out = self.scope.gen_sym(self.name + '_io_req')
        req_out_var = AHDL_VAR(req_out)
        
        req_ors = branches['req'][0]
        for req in branches['req'][1:]:
            req_ors = AHDL_OP('Or', req_ors, req)
        self.module_info.add_static_assignment(AHDL_ASSIGN(req_out_var, req_ors))

        # make mux for input ports
        addr_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_addr_selector'))
        mux = AHDL_MUX(addr_selector, selector_var, branches['addr'], trunk['addr'], addr_width)
        self.module_info.add_mux(mux)

        d_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_d_selector'))
        mux = AHDL_MUX(d_selector, selector_var, branches['d'], trunk['d'], INT_WIDTH)
        self.module_info.add_mux(mux)
        
        we_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_we_selector'))
        mux = AHDL_MUX(we_selector, selector_var, branches['we'], trunk['we'], 1)
        self.module_info.add_mux(mux)

        # make demux for output port
        q_selector = AHDL_VAR(self.scope.gen_sym(mux_prefix + '_q_selector'))
        demux = AHDL_DEMUX(q_selector, selector_var, trunk['q'], branches['q'], INT_WIDTH)
        self.module_info.add_demux(demux)


class LeafMemPortMaker(HDLMemPortMaker):
    def __init__(self, meminfo, scope, module_info):
        super().__init__(meminfo, scope, module_info)

    def make_hdl(self):
        self._make_access_ports()

    def _make_access_ports(self):
        #input port
        self.module_info.add_input(self.name + '_q', 'wire', self.meminfo.width)
        #output port
        self.module_info.add_output(self.name + '_req', 'reg', 1)
        self.module_info.add_output(self.name + '_d', 'reg', self.meminfo.width)
        self.module_info.add_output(self.name + '_addr', 'reg', self.addr_width)
        self.module_info.add_output(self.name + '_we', 'reg', 1)

