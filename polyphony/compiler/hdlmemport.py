from collections import OrderedDict, namedtuple, defaultdict
from .hdlmoduleinfo import HDLModuleInfo
from .env import env
from .common import INT_WIDTH
from .ahdl import AHDL_CONST, AHDL_VAR, AHDL_CONCAT, AHDL_OP, AHDL_IF_EXP, AHDL_ASSIGN, AHDL_CONNECT, AHDL_FUNCALL, AHDL_FUNCTION, AHDL_CASE, AHDL_CASE_ITEM, AHDL_MUX, AHDL_DEMUX
from . import libs
from logging import getLogger, DEBUG
logger = getLogger(__name__)


Port = namedtuple('Port', ('postfix', 'typ', 'width', 'sign'))
Signal = namedtuple('Signal', ('postfix', 'width'))


class HDLMemPortMaker:
    @classmethod
    def create(cls, memnode, scope, module_info):
        if memnode.param_index < 0:
            if memnode.succs:
                return RootMemPortMaker(memnode, scope, module_info)
            else:
                return DirectMemPortMaker(memnode, scope, module_info)
        else:
            if memnode.succs:
                return BranchMemPortMaker(memnode, scope, module_info)
            else:
                return LeafMemPortMaker(memnode, scope, module_info)

    def __init__(self, memnode, scope, module_info):
        self.memnode = memnode
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
            postfix = '_br'
        else:
            postfix = ''
        _, port_data_width, port_addr_width = cls.get_safe_sizes(env.memref_graph, callee_memnode)
        ports = [
            Port('q',    'wire', port_data_width, 'signed'),
            Port('len',  'wire', port_addr_width, ''),
            Port('d',    'wire', port_data_width, 'signed'),
            Port('addr', 'wire', port_addr_width, ''),
            Port('we',   'wire', 1, 'signed'),
            Port('req',  'wire', 1, 'signed')
        ]
        for port in ports:
            port_map[dst_name + '_' + port.postfix + postfix] =  src_name + '_' + port.postfix

        cls._add_internals(module_info, src_name, ports)
        if len(caller_memnodes) <= 1:
            return

        branch_names = []
        for memnode in caller_memnodes:
            each_caller_name = '{}_{}_{}'.format(callee_instance, callee_memnode.param_index, memnode.sym.hdl_name())
            branch_names.append(each_caller_name)
            cls._add_internals(module_info,
                               each_caller_name,
                               ports)
            csname = each_caller_name + '_cs'
            module_info.add_internal_reg(csname, 1, '')

        signals = [
            Signal('addr', port_addr_width),
            Signal('d', port_data_width),
            Signal('q', port_data_width),
            Signal('len', port_addr_width),
            Signal('we', 1),
            Signal('req', 1),
            Signal('cs', 1)
        ]

        trunk = {}
        for s in signals:
            sym = scope.gen_sym(src_name + '_' + s.postfix)
            sym.width = s.width
            trunk[s.postfix] = sym

        branches = defaultdict(list)
        for branch in branch_names:
            for s in signals:
                sym = scope.gen_sym(branch + '_' + s.postfix)
                sym.width = s.width
                if sym not in branches[s.postfix]:
                    branches[s.postfix].append(sym)
            
        #assign selector = {req0, req1, ...}
        sel = scope.gen_sym(src_name + '_select_sig')
        sel.width = len(branches['cs'])
        selector_var = AHDL_VAR(sel)
        chipselect_bits = AHDL_CONCAT(reversed([AHDL_VAR(cs) for cs in branches['cs']]))
        module_info.add_static_assignment(AHDL_ASSIGN(selector_var, chipselect_bits))
        module_info.add_internal_wire(sel.name, sel.width, '')

        # make demux for input ports
        addr_selector = AHDL_VAR(scope.gen_sym(src_name + '_addr_selector'))
        demux = AHDL_DEMUX(addr_selector, selector_var, trunk['addr'], branches['addr'], port_addr_width)
        module_info.add_demux(demux)

        d_selector = AHDL_VAR(scope.gen_sym(src_name + '_d_selector'))
        demux = AHDL_DEMUX(d_selector, selector_var, trunk['d'], branches['d'], port_data_width)
        module_info.add_demux(demux)

        we_selector = AHDL_VAR(scope.gen_sym(src_name + '_we_selector'))
        demux = AHDL_DEMUX(we_selector, selector_var, trunk['we'], branches['we'], 1)
        module_info.add_demux(demux)

        req_selector = AHDL_VAR(scope.gen_sym(src_name + '_req_selector'))
        demux = AHDL_DEMUX(req_selector, selector_var, trunk['req'], branches['req'], 1)
        module_info.add_demux(demux)

        # make mux for output port
        q_selector = AHDL_VAR(scope.gen_sym(src_name + '_q_selector'))
        mux = AHDL_MUX(q_selector, selector_var, branches['q'], trunk['q'], port_data_width)
        module_info.add_mux(mux)

        len_selector = AHDL_VAR(scope.gen_sym(src_name + '_len_selector'))
        mux = AHDL_MUX(len_selector, selector_var, branches['len'], trunk['len'], port_addr_width)
        module_info.add_mux(mux)

    @classmethod
    def get_safe_sizes(cls, mrg, memnode):
        memroot = mrg.get_single_root(memnode)
        if memroot:
            return memroot.length, memroot.width, memroot.length.bit_length()+1
        else:
            return -1, 32, 13

    @classmethod
    def _add_internals(cls, module_info, prefix, ports):
        for port in ports:
            name = prefix + '_' + port.postfix
            if port.typ == 'wire':
                module_info.add_internal_wire(name, port.width, port.sign)
            else:
                module_info.add_internal_reg(name, port.width, port.sign)




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
            Port('q',    'wire', width, 'signed'),
            Port('len',  'wire', addr_width, ''),
            Port('d',    'reg', width, 'signed'),
            Port('addr', 'reg', addr_width, ''),
            Port('we',   'reg', 1, 'signed'),
            Port('req',  'reg', 1, 'signed')
        ]
        self._add_internals(self.module_info, self.name, ports)


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
            Port('q_ram',    'wire', width, 'signed'),
            Port('len_ram',  'wire', addr_width, ''),
            Port('d_ram',    'wire', width, 'signed'),
            Port('addr_ram', 'wire', addr_width, ''),
            Port('we_ram',   'wire', 1, 'signed')
        ]
        self._add_internals(self.module_info, self.name, ports)

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
            Port('q',    'wire', width, 'signed'),
            Port('len',  'wire', addr_width, ''),
            Port('d',    'reg', width, 'signed'),
            Port('addr', 'reg', addr_width, ''),
            Port('we',   'reg', 1, 'signed'),
            Port('req',  'reg', 1, 'signed')
        ]
        self._add_internals(self.module_info, self.name, ports)

    def _make_connection(self):
        addr_width = self.addr_width
        data_width = INT_WIDTH #TODO

        src_prefix = self.name

        signals = [
            Signal('addr', addr_width),
            Signal('d', data_width),
            Signal('q', data_width),
            Signal('len', addr_width),
            Signal('we', 1),
            Signal('req', 1)
        ]

        trunk = {}
        for s in signals:
            sym = self.scope.gen_sym(src_prefix + '_' + s.postfix + '_ram')
            sym.width = s.width
            trunk[s.postfix] = sym

        branches = defaultdict(list)
        for s in signals:
            sym = self.scope.gen_sym(src_prefix + '_' + s.postfix)
            sym.width = s.width
            if sym not in branches[s.postfix]:
                branches[s.postfix].append(sym)

        for inst, succ in self.mrg.collect_inst_succs(self.memnode):
            dst_prefix = '{}_{}_{}'.format(inst, succ.param_index, self.name)
            for s in signals:
                sym = self.scope.gen_sym(dst_prefix + '_' + s.postfix)
                sym.width = s.width
                if sym not in branches[s.postfix]:
                    branches[s.postfix].append(sym)

        #assign selector = {req0, req1, ...}                
        sel = self.scope.gen_sym(src_prefix + '_select_sig_ram')
        sel.width = len(branches['req'])
        selector_var = AHDL_VAR(sel)
        request_bits = AHDL_CONCAT(reversed([AHDL_VAR(req) for req in branches['req']]))
        self.module_info.add_static_assignment(AHDL_ASSIGN(selector_var, request_bits))
        self.module_info.add_internal_wire(sel.name, sel.width, '')

        # make mux for input ports
        addr_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_addr_selector_ram'))
        mux = AHDL_MUX(addr_selector, selector_var, branches['addr'], trunk['addr'], addr_width)
        self.module_info.add_mux(mux)

        d_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_d_selector_ram'))
        mux = AHDL_MUX(d_selector, selector_var, branches['d'], trunk['d'], INT_WIDTH)
        self.module_info.add_mux(mux)
        
        we_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_we_selector_ram'))
        mux = AHDL_MUX(we_selector, selector_var, branches['we'], trunk['we'], 1)
        self.module_info.add_mux(mux)

        # make demux for output port
        q_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_q_selector_ram'))
        demux = AHDL_DEMUX(q_selector, selector_var, trunk['q'], branches['q'], INT_WIDTH)
        self.module_info.add_demux(demux)

        for branch_len in branches['len']:
            self.module_info.add_static_assignment(AHDL_ASSIGN(AHDL_VAR(branch_len), AHDL_VAR(trunk['len'])))


class BranchMemPortMaker(HDLMemPortMaker):
    def __init__(self, memnode, scope, module_info):
        super().__init__(memnode, scope, module_info)

    def make_hdl(self):
        self._make_access_ports()
        self._make_connection()

    def _make_access_ports(self):
        width = INT_WIDTH
        addr_width = self.addr_width
        #input port
        self.module_info.add_input(self.name + '_q_br', 'wire', width)
        self.module_info.add_input(self.name + '_len_br', 'wire', addr_width)
        #output port
        self.module_info.add_output(self.name + '_req_br', 'wire', 1)
        self.module_info.add_output(self.name + '_d_br', 'wire', width)
        self.module_info.add_output(self.name + '_addr_br', 'wire', addr_width)
        self.module_info.add_output(self.name + '_we_br', 'wire', 1)

        #internal ports
        ports = [
            Port('q',    'wire', width, 'signed'),
            Port('len',  'wire', addr_width-1, ''),
            Port('d',    'reg', width, 'signed'),
            Port('addr', 'reg', addr_width, ''),
            Port('we',   'reg', 1, 'signed'),
            Port('req',  'reg', 1, 'signed')
        ]
        self._add_internals(self.module_info, self.name, ports)

    def _make_connection(self):
        addr_width = self.addr_width
        data_width = INT_WIDTH #TODO

        src_prefix = self.name

        signals = [
            Signal('addr', addr_width),
            Signal('d', data_width),
            Signal('q', data_width),
            Signal('len', addr_width),
            Signal('we', 1),
            Signal('req', 1)
        ]

        trunk = {}
        for s in signals:
            sym = self.scope.gen_sym(src_prefix + '_' + s.postfix + '_br')
            sym.width = s.width
            trunk[s.postfix] = sym

        branches = defaultdict(list)
        for s in signals:
            sym = self.scope.gen_sym(src_prefix + '_' + s.postfix)
            sym.width = s.width
            if sym not in branches[s.postfix]:
                branches[s.postfix].append(sym)

        for inst, succ in self.mrg.collect_inst_succs(self.memnode):
            dst_prefix = '{}_{}_{}'.format(inst, succ.param_index, self.name)
            for s in signals:
                sym = self.scope.gen_sym(dst_prefix + '_' + s.postfix)
                sym.width = s.width
                if sym not in branches[s.postfix]:
                    branches[s.postfix].append(sym)

        #assign selector = {req0, req1, ...}                
        sel = self.scope.gen_sym(src_prefix + '_select_sig_br')
        sel.width = len(branches['req'])
        selector_var = AHDL_VAR(sel)
        request_bits = AHDL_CONCAT(reversed([AHDL_VAR(req) for req in branches['req']]))
        self.module_info.add_static_assignment(AHDL_ASSIGN(selector_var, request_bits))
        self.module_info.add_internal_wire(sel.name, sel.width, '')

        req_out = self.scope.gen_sym(self.name + '_req_br')
        req_out_var = AHDL_VAR(req_out)
        
        req_ors = AHDL_VAR(branches['req'][0])
        for req in branches['req'][1:]:
            req_ors = AHDL_OP('Or', req_ors, AHDL_VAR(req))
        self.module_info.add_static_assignment(AHDL_ASSIGN(req_out_var, req_ors))

        # make mux for input ports
        addr_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_addr_selector_br'))
        mux = AHDL_MUX(addr_selector, selector_var, branches['addr'], trunk['addr'], addr_width)
        self.module_info.add_mux(mux)

        d_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_d_selector_br'))
        mux = AHDL_MUX(d_selector, selector_var, branches['d'], trunk['d'], INT_WIDTH)
        self.module_info.add_mux(mux)
        
        we_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_we_selector_br'))
        mux = AHDL_MUX(we_selector, selector_var, branches['we'], trunk['we'], 1)
        self.module_info.add_mux(mux)

        # make demux for output port
        q_selector = AHDL_VAR(self.scope.gen_sym(src_prefix + '_q_selector_br'))
        demux = AHDL_DEMUX(q_selector, selector_var, trunk['q'], branches['q'], INT_WIDTH)
        self.module_info.add_demux(demux)

        for branch_len in branches['len']:
            self.module_info.add_static_assignment(AHDL_ASSIGN(AHDL_VAR(branch_len), AHDL_VAR(trunk['len'])))

class LeafMemPortMaker(HDLMemPortMaker):
    def __init__(self, memnode, scope, module_info):
        super().__init__(memnode, scope, module_info)

    def make_hdl(self):
        self._make_access_ports()

    def _make_access_ports(self):
        #input port
        self.module_info.add_input(self.name + '_q', 'wire', self.width)
        self.module_info.add_input(self.name + '_len', 'wire', self.addr_width)
        #output port
        self.module_info.add_output(self.name + '_req', 'reg', 1)
        self.module_info.add_output(self.name + '_d', 'reg', self.width)
        self.module_info.add_output(self.name + '_addr', 'reg', self.addr_width)
        self.module_info.add_output(self.name + '_we', 'reg', 1)

