from collections import OrderedDict
from .verilog_common import pyop2verilogop
from .ir import Ctx
from .signal import Signal
from .ahdl import *
from .env import env
from .common import INT_WIDTH
from .type import Type
from .hdlinterface import *
from .memref import One2NMemNode, N2OneMemNode
from logging import getLogger
logger = getLogger(__name__)


class VerilogCodeGen:
    def __init__(self, scope):
        self.codes = []
        self.indent = 0
        self.scope = scope
        self.module_info = self.scope.module_info

    def result(self):
        return ''.join(self.codes)

    def emit(self, code, with_indent=True, newline=True):
        if with_indent:
            self.codes.append((' '*self.indent) + code)
        else:
            self.codes.append(code)
        if newline:
            self.codes.append('\n')

    def tab(self):
        return ' '*self.indent
    
    def set_indent(self, val):
        self.indent += val

    def generate(self):
        """
        output verilog module format:

        module {module_name}
        {params}
        {portdefs}
        {localparams}
        {internal_regs}
        {internal_nets}
        {functions}
        {fsm}
        endmodule
        """

        self.set_indent(2)
        for fsm in self.module_info.fsms.values():
            self._generate_process(fsm)
        self.set_indent(-2)
        main_code = self.result()
        self.codes = []

        self._generate_include()
        self._generate_module()
        self.emit(main_code)
        self.emit('endmodule\n')

    def _generate_process(self, fsm):
        self.emit('always @(posedge clk) begin')
        self.set_indent(2)
        self.emit('if (rst) begin')
        self.set_indent(2)

        for stg in fsm.stgs:
            if stg.is_main():
                main_stg = stg
        assert main_stg

        for sig in fsm.outputs:
            if sig.is_reg():
                self.emit('{} <= 0;'.format(sig.name))

        self.current_state_sig = fsm.state_var
        self.emit('{} <= {};'.format(self.current_state_sig.name, main_stg.init_state.name))
        self.set_indent(-2)
        self.emit('end else begin //if (rst)')
        self.set_indent(2)

        self.emit('case({})'.format(self.current_state_sig.name))

        for stg in fsm.stgs:
            for i, state in enumerate(stg.states):
                self._process_State(state)

        self.emit('endcase')
        self.set_indent(-2)
        self.emit('end')#end if (READY)
        self.set_indent(-2)
        self.emit('end')
        self.emit('')

    def _generate_include(self):
        pass
        # self.emit('`include "SinglePortRam.v"')

    def _generate_module(self):
        self._generate_module_header()
        self.set_indent(2)
        self._generate_localparams()
        self._generate_decls()
        self._generate_sub_module_instances()        
        self._generate_field_access()
        self._generate_net_monitor()
        self.set_indent(-2)

    def _generate_module_header(self):
        self.emit('module {}'.format(self.module_info.qualified_name))
        
        self.set_indent(2)
        self.emit('(')
        self.set_indent(2)

        self._generate_io_port()
        self.set_indent(-2)
        self.emit(');')
        self.set_indent(-2)
        self.emit('')

    def _generate_io_port(self):
        ports = []
        if not self.scope.is_testbench():
            ports.append('input wire clk')
            ports.append('input wire rst')
        for i in self.module_info.interfaces:
            if not i.is_public:
                continue
            for p in i.ports:
                ports.append(self._to_io_name(self.module_info.name, i, p))
        self.emit((',\n'+self.tab()).join(ports))
        self.emit('')
                
    def _generate_signal(self, sig):
        sign = 'signed' if sig.is_int() else ''
        return '{:<6} [{}:0] {}'.format(sign, sig.width-1, sig.name)

    def _generate_localparams(self):
        constants = self.module_info.constants + self.module_info.state_constants
        if not constants:
            return
        self.emit('//localparams')
        for name, val in constants:
            self.emit('localparam {0} = {1};'.format(name, val))
        self.emit('')

    def _generate_net_monitor(self):
        if env.hdl_debug_mode and not self.scope.is_testbench():
            self.emit('always @(posedge clk) begin')
            self.emit('if (rst==0 && {}!={}) begin'.format(self.current_state_sig.name, 0))
            for tag, decls in self.module_info.decls.items():
                nets = [decl for decl in decls if isinstance(decl, AHDL_NET_DECL)]
                for net in nets:
                    if net.sig.is_onehot():
                        self.emit('$display("%8d:WIRE  :{}      {} = 0b%b", $time, {});'.format(self.scope.orig_name, net.sig, net.sig))
                    else:
                        self.emit('$display("%8d:WIRE  :{}      {} = 0x%2h (%1d)", $time, {}, {});'.format(self.scope.orig_name, net.sig, net.sig, net.sig))
            self.emit('end')
            self.emit('end')
            self.emit('')

        self.emit('')

    def _generate_decls(self):
        for tag, decls in sorted(self.module_info.decls.items()):
            decls = [decl for decl in decls if isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit('//signals: {}'.format(tag))
                for decl in decls:
                    self.visit(decl)
        for tag, decls in sorted(self.module_info.decls.items()):
            decls = [decl for decl in decls if not isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit('//combinations: {}'.format(tag))
                for decl in decls:
                    self.visit(decl)

    def _to_io_name(self, module_name, interface, port):
        io = 'input' if port.dir=='in' else 'output'
        typ = 'wire' if port.dir=='in' or interface.thru or isinstance(interface, InstanceInterface) else 'reg'
        port_name = interface.port_name(module_name, port)

        if port.width == 1:
            ioname = '{} {} {}'.format(io, typ, port_name)
        else:
            ioname = '{} {} signed [{}:0] {}'.format(io, typ, port.width-1, port_name)
        return ioname

    def _to_signal_name(self, instance_name, interface, port):
        accessor_name = interface.port_name(instance_name, port)
        typ = 'reg' if port.dir=='in' and not interface.thru else 'wire'
        if port.width == 1:
            signame = '{} {};\n'.format(typ, accessor_name)
        else:
            signame = '{} signed [{}:0] {};\n'.format(typ, port.width-1, accessor_name)
        return signame

    def _to_sub_module_connect(self, module_name, instance_name, interface, port):
        port_name = interface.port_name(module_name, port)
        accessor_name = interface.port_name("sub_"+instance_name, port)# self._accessor_name(instance_name, interface, port)
        connection = '.{}({})'.format(port_name, accessor_name)
        return connection
                
    def _generate_sub_module_instances(self):
        if not self.module_info.sub_modules:
            return
        self.emit('//sub modules')
        for name, info, accessors, sub_infs, param_map in self.module_info.sub_modules.values():
            ports = []
            ports.append('.clk(clk)')
            ports.append('.rst(rst)')
            for i in info.interfaces:
                if not i.is_public:
                    continue
                for p in i.ports:
                    ports.append(self._to_sub_module_connect(info.name, name, i, p))

            self.emit('//{} instance'.format(name))
            #for port, signal in port_map.items():
            #    ports.append('.{}({})'.format(port, signal))
            if param_map:
                params = []
                for param_name, value in param_map.items():
                    params.append('.{}({})'.format(param_name, value))

                self.emit('{}#('.format(info.qualified_name))
                self.set_indent(2)
                self.emit('{}'.format((',\n'+self.tab()).join(params)))
                self.emit(')')
                self.emit('{}('.format(name))
                self.set_indent(2)
                self.emit('{}'.format((',\n'+self.tab()).join(ports)))
                self.set_indent(-2)
                self.emit(');')
                self.set_indent(-2)
            else:
                self.emit('{} {}('.format(info.qualified_name, name))
                self.set_indent(2)
                self.emit('{}'.format((',\n'+self.tab()).join(ports)))
                self.set_indent(-2)
                self.emit(');')
        self.emit('')

    def _generate_reg_field_access(self, fieldif):
        conds = []
        codes_list = []
        field_name = self.module_info.name + '_' + fieldif.name
        if field_name in self.module_info.internal_field_accesses:
            for method_scope, state, ahdl in self.module_info.internal_field_accesses[field_name]:
                state_var = self.module_info.fsms[method_scope.name].state_var
                cond = AHDL_OP('Eq', AHDL_VAR(state_var, Ctx.LOAD), AHDL_SYMBOL(state.name))
                conds.append(cond)
                codes_list.append([ahdl])
            
        field       = field_name
        field_in    = field + '_in'
        field_ready = field + '_ready'
        cond = AHDL_OP('Eq', AHDL_SYMBOL(field_ready), AHDL_CONST(1))
        conds.append(cond)
        mv = AHDL_MOVE(AHDL_SYMBOL(field), AHDL_SYMBOL(field_in))
        codes_list.append([mv])
           
        conds.append(AHDL_CONST(1))
        mv = AHDL_MOVE(AHDL_SYMBOL(field), AHDL_SYMBOL(field))
        codes_list.append([mv])

        ifexp = AHDL_IF(conds, codes_list)
        
        self.emit('/* field access for {}.{}*/'.format(self.module_info.name, fieldif.field_name))    
        self.emit('always @(posedge clk) begin: {}_access'.format(field_name))
        self.set_indent(2)
        self.emit('if (rst) begin')
        self.set_indent(2)
        self.emit('{} <= 0;'.format(field))
        self.set_indent(-2)
        self.emit('end else begin')
        self.set_indent(2)
        self.visit(ifexp)
        self.set_indent(-2)
        self.emit('end /* if (rst) */')
        self.set_indent(-2)
        self.emit('end /* always */')
        self.emit('')

    def _generate_ram_field_access(self, fieldif):
        conds = []
        codes_list = []
        field_name = self.module_info.name + '_' + fieldif.name
        if field_name in self.module_info.internal_field_accesses:
            for method_scope, state, ahdl in self.module_info.internal_field_accesses[field_name]:
                state_var = self.module_info.fsms[method_scope.name].state_var
                cond = AHDL_OP('Eq', AHDL_VAR(state_var, Ctx.LOAD), AHDL_SYMBOL(state.name))
                conds.append(cond)
                codes_list.append([ahdl])
        
        field       = field_name
        #field_in    = field + '_in'
        #field_ready = field + '_ready'
        #cond = AHDL_OP('Eq', AHDL_SYMBOL(field_ready), AHDL_CONST(1))
        #conds.append(cond)
        #mv = AHDL_MOVE(AHDL_SYMBOL(field), AHDL_SYMBOL(field_in))
        #codes_list.append([mv])
           
        #conds.append(AHDL_CONST(1))
        #mv = AHDL_MOVE(AHDL_SYMBOL(field), AHDL_SYMBOL(field))
        #codes_list.append([mv])

        ifexp = AHDL_IF(conds, codes_list)
        
        self.emit('/* field access for {}.{}*/'.format(self.module_info.name, fieldif.field_name))    
        self.emit('always @(posedge clk) begin: {}_access'.format(field_name))
        self.set_indent(2)
        self.emit('if (rst) begin')
        self.set_indent(2)
        #self.emit('{} <= 0;'.format(field))
        self.set_indent(-2)
        self.emit('end else begin')
        self.set_indent(2)
        self.visit(ifexp)
        self.set_indent(-2)
        self.emit('end /* if (rst) */')
        self.set_indent(-2)
        self.emit('end /* always */')
        self.emit('')

    def _generate_instance_field_access(self, fieldif):
        conds = []
        codes_list = []
        if False:#self.scope.is_class():
            field_name = self.module_info.name + '_' + fieldif.name
        else:
            field_name = fieldif.name
        if field_name in self.module_info.internal_field_accesses:
            for caller_scope, state, ahdl in self.module_info.internal_field_accesses[field_name]:
                state_var = self.module_info.fsms[caller_scope.name].state_var
                cond = AHDL_OP('Eq', AHDL_VAR(state_var, Ctx.LOAD), AHDL_SYMBOL(state.name))
                conds.append(cond)
                codes_list.append([ahdl])
        else:
            return
        ifexp = AHDL_IF(conds, codes_list)
        
        self.emit('/* field access for {}.{}*/'.format(fieldif.inst_name, fieldif.inf.name))
        self.emit('always @(posedge clk) begin: {}_access'.format(field_name))
        self.set_indent(2)
        self.emit('if (rst) begin')
        self.set_indent(2)
        for p in fieldif.inports():
            name = fieldif.port_name('', p)
            self.emit('{} <= 0;'.format(name))
        self.set_indent(-2)
        self.emit('end else begin /* if (rst) */')
        self.set_indent(2)
        self.visit(ifexp)
        self.set_indent(-2)
        self.emit('end /* if (rst) */')
        self.set_indent(-2)
        self.emit('end /* always */')
        self.emit('')

    def _generate_field_access(self):
        for inf in self.module_info.interfaces:
            if isinstance(inf, RegFieldInterface):
                self._generate_reg_field_access(inf)
            elif isinstance(inf, RAMFieldInterface):
                self._generate_ram_field_access(inf)
            elif isinstance(inf, InstanceInterface):
                self._generate_instance_field_access(inf)

    def _process_State(self, state):
        self.current_state = state
        code = '{0}: begin'.format(state.name)
        self.emit(code)
        self.set_indent(2)
        if env.hdl_debug_mode:
            self.emit('$display("%8d:STATE:{}  {}", $time);'.format(self.scope.orig_name, state.name))

        for code in state.codes:
            self.visit(code)

        self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_CONST(self, ahdl):
        if ahdl.value is None:
            return "'bx";
        elif isinstance(ahdl.value, bool):
            return str(int(ahdl.value))
        elif isinstance(ahdl.value, str):
            return '"' + ahdl.value +'"'
        return str(ahdl.value)

    def visit_AHDL_VAR(self, ahdl):
        return ahdl.sig.name

    def visit_AHDL_MEMVAR(self, ahdl):
        assert 0

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        return '{}[{}]'.format(ahdl.memvar.sig.name, self.visit(ahdl.offset))

    def visit_AHDL_SYMBOL(self, ahdl):
        return ahdl.name

    def visit_AHDL_CONCAT(self, ahdl):
        if ahdl.op:
            code = PYTHON_OP_2_HDL_OP_MAP[ahdl.op].join([str(v) for v in ahdl.varlist])
        else:
            code = '{'
            code += ', '.join([self.visit(var) for var in ahdl.varlist])
            code += '}'
        return code

    def visit_AHDL_OP(self, ahdl):
        if ahdl.right:
            left = self.visit(ahdl.left)
            right = self.visit(ahdl.right)
            return '({} {} {})'.format(left, pyop2verilogop(ahdl.op), right)
        else:
            exp = self.visit(ahdl.left)
            return '{}{}'.format(pyop2verilogop(ahdl.op), exp)
            
    def visit_AHDL_NOP(self, ahdl):
        if isinstance(ahdl.info, AHDL):
            self.emit('/*')
            self.visit(ahdl.info)
            self.emit('*/')
        else:
            self.emit('/*' + str(ahdl.info) + '*/')
        
    def _memswitch(self, prefix, dst_node, src_node):
        n2o = dst_node.pred_branch()
        assert isinstance(n2o, N2OneMemNode)
        for p in n2o.preds:
            assert isinstance(p, One2NMemNode)
        assert isinstance(src_node.preds[0], One2NMemNode)
        assert src_node in n2o.orig_preds
        
        preds = [p for p in n2o.preds if self.scope in p.scopes]
        width = len(preds)
        if width < 2:
            return
        orig_preds = [p for p in n2o.orig_preds if self.scope in p.scopes]
        idx = orig_preds.index(src_node)
        cs_name = dst_node.name()
        if prefix:
            cs = self.scope.gen_sig('{}_{}_cs'.format(prefix, cs_name), width)
        else:
            cs = self.scope.gen_sig('{}_cs'.format(cs_name), width)
        one_hot_mask = bin(1 << idx)[2:]
        self.visit(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE), AHDL_SYMBOL('\'b'+one_hot_mask)))


    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR) and ahdl.dst.sig.is_condition():
            self.module_info.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
        elif ahdl.dst.is_a(AHDL_MEMVAR) and ahdl.src.is_a(AHDL_MEMVAR):
            memnode = ahdl.dst.memnode
            assert memnode
            if memnode.is_joinable() and not memnode.is_immutable():
                self._memswitch('', ahdl.dst.memnode, ahdl.src.memnode)
        else:
            src = self.visit(ahdl.src)
            dst = self.visit(ahdl.dst)
            if env.hdl_debug_mode:
                self.emit('$display("%8d:REG  :{}      {} <= 0x%2h (%1d)", $time, {}, {});'.format(self.scope.orig_name, dst, src, src))
            self.emit('{} <= {};'.format(dst, src))

    def _memif_names(self, sig, memnode):
        memname = sig.name
        if memnode.is_param():
            prefix = self.module_info.name + '_' + memname
        else:
            prefix = memname
        req  = '{}_{}'.format(prefix, 'req')
        addr = '{}_{}'.format(prefix, 'addr')
        we   = '{}_{}'.format(prefix, 'we')
        d    = '{}_{}'.format(prefix, 'd')
        q    = '{}_{}'.format(prefix, 'q')
        len  = '{}_{}'.format(prefix, 'len')
        return (req, addr, we, d, q, len)

    def _is_sequential_access_to_mem(self, ahdl):
        other_memnodes = [c.mem.memnode for c in self.current_state.codes \
                       if c.is_a([AHDL_STORE, AHDL_LOAD]) and c is not ahdl]
        for memnode in other_memnodes:
            if memnode is ahdl.mem.memnode:
                return True
        return False
        
    def visit_AHDL_STORE(self, ahdl):
        req, addr, we, d, _, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(AHDL_SYMBOL(addr), ahdl.offset))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(we), AHDL_CONST(1)))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(1)))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(d), ahdl.src))

    def visit_POST_AHDL_STORE(self, ahdl):
        if self._is_sequential_access_to_mem(ahdl):
            return
        req, _, _, _, _, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(0)))

    def visit_AHDL_LOAD(self, ahdl):
        req, addr, we, _, _, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(AHDL_SYMBOL(addr), ahdl.offset))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(we), AHDL_CONST(0)))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(1)))

    def visit_POST_AHDL_LOAD(self, ahdl):
        req, _, _, _, q, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(ahdl.dst, AHDL_SYMBOL(q)))
        if self._is_sequential_access_to_mem(ahdl):
            return
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(0)))


    def visit_AHDL_FIELD_MOVE(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        if env.hdl_debug_mode:
            self.emit('$display("%8d:REG  :{}      {} <= 0x%2h (%1d)", $time, {}, {});'.format(self.scope.orig_name, dst, src, src))
        self.emit('{} <= {};'.format(dst, src))

        if ahdl.is_ext:
            field_ready = '{}_field_{}_ready'.format(ahdl.inst_name, ahdl.attr_name)
            self.visit(AHDL_MOVE(AHDL_SYMBOL(field_ready), AHDL_CONST(1)))

    def visit_POST_AHDL_FIELD_MOVE(self, ahdl):
        field_ready = '{}_field_{}_ready'.format(ahdl.inst_name, ahdl.attr_name)
        self.visit(AHDL_MOVE(AHDL_SYMBOL(field_ready), AHDL_CONST(0)))

    def visit_AHDL_FIELD_STORE(self, ahdl):
        req, addr, we, d, _, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(AHDL_SYMBOL(addr), ahdl.offset))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(we), AHDL_CONST(1)))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(1)))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(d), ahdl.src))

    def visit_POST_AHDL_FIELD_STORE(self, ahdl):
        if self._is_sequential_access_to_mem(ahdl):
            return
        req, _, _, _, _, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(0)))

    def visit_AHDL_FIELD_LOAD(self, ahdl):
        req, addr, we, _, _, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(AHDL_SYMBOL(addr), ahdl.offset))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(we), AHDL_CONST(0)))
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(1)))

    def visit_POST_AHDL_FIELD_LOAD(self, ahdl):
        req, _, _, _, q, _ = self._memif_names(ahdl.mem.sig, ahdl.mem.memnode)
        self.visit(AHDL_MOVE(ahdl.dst, AHDL_SYMBOL(q)))
        if self._is_sequential_access_to_mem(ahdl):
            return
        self.visit(AHDL_MOVE(AHDL_SYMBOL(req), AHDL_CONST(0)))

    def visit_AHDL_POST_PROCESS(self, ahdl):
        method = 'visit_POST_' + ahdl.factor.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ahdl.factor)

    def visit_AHDL_MEM(self, ahdl):
        name = ahdl.name.hdl_name()
        offset = self.visit(ahdl.offset)
        return '{}[{}]'.format(name, offset)

    def visit_AHDL_IF(self, ahdl):
        cond0 = self.visit(ahdl.conds[0])
        if cond0[0] != '(':
            cond0 = '('+cond0+')'
        self.emit('if {} begin'.format(cond0))
        self.set_indent(2)
        for code in ahdl.codes_list[0]:
            self.visit(code)
        self.set_indent(-2)
        for cond, codes in zip(ahdl.conds[1:], ahdl.codes_list[1:]):
            if cond:
                cond = self.visit(cond)
                if cond[0] != '(':
                    cond = '('+cond+')'
                self.emit('end else if {} begin'.format(cond))
                self.set_indent(2)
                for code in codes:
                    self.visit(code)
                self.set_indent(-2)
            else:
                self.emit('end else begin')
                self.set_indent(2)
                for code in ahdl.codes_list[-1]:
                    self.visit(code)
                self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_IF_EXP(self, ahdl):
        cond = self.visit(ahdl.cond)
        lexp = self.visit(ahdl.lexp)
        rexp = self.visit(ahdl.rexp)
        return '{} ? {} : {}'.format(cond, lexp, rexp)

    def visit_AHDL_MODULECALL(self, ahdl):
        if ahdl.scope.is_class():
            params = ahdl.scope.find_ctor().params[1:]
        elif ahdl.scope.is_method():
            params = ahdl.scope.params[1:]
        else:
            params = ahdl.scope.params
        for arg, param in zip(ahdl.args, params):
            p, _, _ = param            
            if arg.is_a(AHDL_MEMVAR):
                assert Type.is_seq(p.typ)
                param_memnode = Type.extra(p.typ)
                # find joint node in outer scope
                assert len(param_memnode.preds) == 1
                is_joinable_param = isinstance(param_memnode.preds[0], N2OneMemNode)
                if is_joinable_param and param_memnode.is_writable():
                    self._memswitch(ahdl.instance_name, param_memnode, arg.memnode)
            else:
                argsig = self.scope.gen_sig('{}_{}'.format(ahdl.prefix, p.hdl_name()), INT_WIDTH, ['int'])
                self.visit(AHDL_MOVE(AHDL_VAR(argsig, Ctx.STORE), arg))

        ready = self.scope.gen_sig(ahdl.prefix + '_ready', 1)
        self.visit(AHDL_MOVE(AHDL_VAR(ready, Ctx.STORE), AHDL_CONST(1)))

    def visit_AHDL_FUNCALL(self, ahdl):
        return '{}({})'.format(ahdl.name, ', '.join([self.visit(arg) for arg in ahdl.args]))

    def visit_AHDL_PROCCALL(self, ahdl):
        args = []
        for arg in ahdl.args:
            a = self.visit(arg)
            args.append(a)

        if ahdl.name == '!hdl_print':
            self.emit('$display("%1d", {});'.format(', '.join(args)))
        elif ahdl.name == '!hdl_verilog_display':
            self.emit('$display({});'.format(', '.join(args)))
        elif ahdl.name == '!hdl_verilog_write':
            self.emit('$write({});'.format(', '.join(args)))
        elif ahdl.name == '!hdl_assert':
            #expand condtion expression for the assert message
            exp = args[0]
            if exp.startswith('cond'):
                remove_assign = []
                for tag, assign in self.module_info.get_static_assignment():
                    if assign.dst.is_a(AHDL_VAR) and assign.dst.sig.name == exp:
                        remove_assign.append((tag, assign))
                        expsig = self.scope.gen_sig(exp, 1)
                        self.module_info.remove_internal_net(expsig)
                        exp = self.visit(assign.src)
                for tag, assign in remove_assign:
                    self.module_info.remove_decl(tag, assign)
            exp = exp.replace('==', '===').replace('!=', '!==')
            code = 'if (!{}) begin'.format(exp)
            self.emit(code)
            code = '  $display("ASSERTION FAILED {}"); $finish;'.format(exp)
            self.emit(code)
            self.emit('end')
        else:
            self.emit('{}({});'.format(ahdl.name, ', '.join(args)))

    def visit_AHDL_REG_DECL(self, ahdl):
        if ahdl.sig.width == 1:
            self.emit('reg {};'.format(ahdl.sig.name))
        else:
            self.emit('reg {};'.format(self._generate_signal(ahdl.sig)))

    def visit_AHDL_REG_ARRAY_DECL(self, ahdl):
        if ahdl.sig.width == 1:
            self.emit('reg {}[0:{}];'.format(ahdl.sig.name, ahdl.size-1))
        else:
            sign = 'signed' if ahdl.sig.is_int() else ''
            self.emit('reg {:<6} [{}:0] {} [0:{}];'.format(sign, ahdl.sig.width-1, ahdl.sig.name, ahdl.size-1))

    def visit_AHDL_NET_DECL(self, ahdl):
        if ahdl.sig.width == 1:
            self.emit('wire {};'.format(ahdl.sig.name))
        else:
            self.emit('wire {};'.format(self._generate_signal(ahdl.sig)))

    def visit_AHDL_NET_ARRAY_DECL(self, ahdl):
        if ahdl.sig.width == 1:
            self.emit('wire {}[0:{}];'.format(ahdl.sig.name, ahdl.size-1))
        else:
            sign = 'signed' if ahdl.sig.is_int() else ''
            self.emit('wire {:<6} [{}:0] {} [0:{}];'.format(sign, ahdl.sig.width-1, ahdl.sig.name, ahdl.size-1))

    def visit_AHDL_ASSIGN(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('assign {} = {};'.format(dst, src))

    def visit_AHDL_CONNECT(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('{} = {};'.format(dst, src))

    def visit_SET_READY(self, ahdl):
        modulecall = ahdl.args[0]
        value = ahdl.args[1]
        ready = self.scope.gen_sig('{}_{}'.format(modulecall.prefix, 'ready'), 1, ['reg'])
        self.visit(AHDL_MOVE(AHDL_VAR(ready, Ctx.STORE), AHDL_CONST(value)))

    def visit_ACCEPT_IF_VALID(self, ahdl):
        modulecall = ahdl.args[0]
        valid = self.scope.gen_sig(modulecall.prefix+'_valid', 1, ['net'])
        accept = self.scope.gen_sig(modulecall.prefix+'_accept', 1, ['reg'])
        cond = AHDL_OP('Eq', AHDL_VAR(valid, Ctx.LOAD), AHDL_CONST(1))
        codes = []
        codes.append(AHDL_MOVE(AHDL_VAR(accept, Ctx.STORE), AHDL_CONST(1)))
        self.visit(AHDL_IF([cond], [codes]))

    def visit_GET_RET_IF_VALID(self, ahdl):
        modulecall = ahdl.args[0]
        dst = ahdl.args[1]
        valid = self.scope.gen_sig(modulecall.prefix+'_valid', 1, ['net'])
        cond = AHDL_OP('Eq', AHDL_VAR(valid, Ctx.LOAD), AHDL_CONST(1))
        codes = []
        sub_out = self.scope.gen_sig(modulecall.prefix+'_out_0', INT_WIDTH, ['net', 'int']) # FIXME '_out_0'
        codes.append(AHDL_MOVE(dst, AHDL_VAR(sub_out, Ctx.LOAD)))
        self.visit(AHDL_IF([cond], [codes]))

    def visit_SET_ACCEPT(self, ahdl):
        modulecall = ahdl.args[0]
        value = ahdl.args[1]
        accept = self.scope.gen_sig('{}_{}'.format(modulecall.prefix, 'accept'), 1, ['reg'])
        self.visit(AHDL_MOVE(AHDL_VAR(accept, Ctx.STORE), AHDL_CONST(value)))

    def visit_AHDL_META(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_WAIT_INPUT_READY(self, ahdl):
        name = ahdl.args[0]
        ready  = AHDL_SYMBOL('{}_{}'.format(name, 'ready'))
        valid  = AHDL_SYMBOL('{}_{}'.format(name, 'valid'))
        conds = [AHDL_OP('Eq', ready, AHDL_CONST(1))]
        if ahdl.codes:
            codes = ahdl.codes[:]
        else:
            codes = []
        codes.append(AHDL_MOVE(valid, AHDL_CONST(0)))
        codes.append(ahdl.transition)
        ahdl_if = AHDL_IF(conds, [codes])
        self.visit(ahdl_if)

    def visit_WAIT_OUTPUT_ACCEPT(self, ahdl):
        name = ahdl.args[0]
        accept  = AHDL_SYMBOL('{}_{}'.format(name, 'accept'))
        valid  = AHDL_SYMBOL('{}_{}'.format(name, 'valid'))

        self.visit(AHDL_MOVE(valid, AHDL_CONST(1)))

        conds = [AHDL_OP('Eq', accept, AHDL_CONST(1))]
        codes_list = [
            [
                ahdl.transition
            ]
        ]
        ahdl_if = AHDL_IF(conds, codes_list)
        self.visit(ahdl_if)

    def visit_WAIT_RET_AND_GATE(self, ahdl):
        conds = []
        for modulecall in ahdl.args[0]:
            valid = self.scope.gen_sig(modulecall.prefix+'_valid', 1, ['net'])
            conds.append(AHDL_OP('Eq', AHDL_VAR(valid, Ctx.LOAD), AHDL_CONST(1)))
        op = conds[0]
        for cond in conds[1:]:
            op = AHDL_OP('And', op, cond)
        ahdl_if = AHDL_IF([op], [[ahdl.transition]])
        self.visit(ahdl_if)

    def visit_AHDL_META_WAIT(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_AHDL_FUNCTION(self, ahdl):
        self.emit('function [{}:0] {} ('.format(ahdl.output.sig.width-1, ahdl.output.sig.name))
        self.set_indent(2)
        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}'.format(input.sig.width-1, input.sig.name))
            else:
                self.emit('input [{}:0] {},'.format(input.sig.width-1, input.sig.name))
        #self.emit(',\n'.join([str(i) for i in ahdl.inputs]))
        self.set_indent(-2)
        self.emit(');')
        self.emit('begin')
        self.set_indent(2)
        for stm in ahdl.stms:
            self.visit(stm)
        self.set_indent(-2)
        self.emit('end')        
        self.emit('endfunction')

    def visit_AHDL_CASE(self, ahdl):
        self.emit('case ({})'.format(self.visit(ahdl.sel)))
        self.set_indent(2)
        for item in ahdl.items:
            self.visit(item)
        self.set_indent(-2)
        self.emit('endcase')

    def visit_AHDL_CASE_ITEM(self, ahdl):
        self.emit("{}:".format(ahdl.val), newline=False)
        self.visit(ahdl.stm)

    def visit_AHDL_MUX(self, ahdl):
        self.emit('function [{}:0] {} ('.format(ahdl.output.width-1, ahdl.name))
        self.set_indent(2)
        
        self.emit('input [{}:0] {},'.format(ahdl.selector.sig.width-1, ahdl.selector.sig.name))
        
        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}'.format(input.width-1, input.name))
            else:
                self.emit('input [{}:0] {},'.format(input.width-1, input.name))
            
        self.set_indent(-2)
        self.emit(');')
        self.emit('begin')
        self.set_indent(2)

        self.emit('case (1\'b1)')
        self.set_indent(2)
        for i, input in enumerate(ahdl.inputs):
            self.emit("{}[{}]: {} = {};".format(ahdl.selector.sig.name, i, ahdl.name, input.name))
        self.set_indent(-2)
        self.emit('endcase')
        self.set_indent(-2)
        self.emit('end')
        self.emit('endfunction')

        params = self.visit(ahdl.selector) + ', '
        params += ', '.join([input.name for input in ahdl.inputs])
        self.emit('assign {} = {}({});'.format(ahdl.output.name, ahdl.name, params))

    def visit_AHDL_DEMUX(self, ahdl):
        if len(ahdl.outputs) > 1:
            for i, output in enumerate(ahdl.outputs):
                if isinstance(ahdl.input, Signal):
                    self.emit('assign {} = 1\'b1 == {}[{}] ? {}:{}\'bz;'.format(output.name, ahdl.selector.sig.name, i, ahdl.input.name, ahdl.input.width))
                elif isinstance(ahdl.input, int):
                    self.emit('assign {} = 1\'b1 == {}[{}] ? {}:{}\'bz;'.format(output.name, ahdl.selector.sig.name, i, ahdl.input, ahdl.width))
        else:
            self.emit('assign {} = {};'.format(ahdl.outputs[0].name, ahdl.input.name))

    def visit_AHDL_TRANSITION(self, ahdl):
        state_var = AHDL_SYMBOL(self.current_state_sig.name)
        state = AHDL_SYMBOL(ahdl.target.name)
        self.visit(AHDL_MOVE(state_var, state))

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit(self, ahdl):
        method = 'visit_' + ahdl.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ahdl)




class VerilogTopGen:

    def __init__(self, mains):
        assert mains
        self.mains = mains
        logger.debug(mains)
        self.name = mains[0].name + '_top'
        self.codes = []
        self.indent = 0

    def result(self):
        return ''.join(self.codes)

    def emit(self, code):
        self.codes.append((' '*self.indent) + code)

    def set_indent(self, val):
        self.indent += val

    def generate(self):
        self.emit(AXI_MODULE_HEADER.format(self.name))
        self._generate_posi_reset()
        self._generate_top_module_instances()

        self.emit('endmodule')

    def _generate_posi_reset(self):
        self.set_indent(2)
        self.emit('wire reset;')
        self.emit('assign reset = !S_AXI_ARESETN;')
        self.emit('')
        self.set_indent(-2)

    def _generate_top_module_instances(self):
        self.set_indent(2)
        self.emit('//main module instances')
        for module_info in self.mains:
            ports = []
            ports.append('.clk(S_AXI_ACLK)')
            ports.append('.rst(reset)')
            #for port, (signal, _, _, _) in port_map.items():
            #    ports.append('.{}({})'.format(port, signal))
            code = '{} {}_inst({});'.format(module_info.name, module_info.name, ', '.join(ports))
            self.emit(code)
        self.set_indent(-2)
        self.emit('')


   
AXI_MODULE_HEADER="""
module {} #
(
  parameter integer C_DATA_WIDTH = 32,
  parameter integer C_ADDR_WIDTH = 4
)
(
  // Ports of Axi Slave Bus Interface S_AXI
  input wire                          S_AXI_ACLK,
  input wire                          S_AXI_ARESETN,
  //Write address channel
  input wire [C_ADDR_WIDTH-1 : 0]     S_AXI_AWADDR,
  input wire [2 : 0]                  S_AXI_AWPROT,
  input wire                          S_AXI_AWVALID,
  output wire                         S_AXI_AWREADY,
  //Write data channel
  input wire [C_DATA_WIDTH-1 : 0]     S_AXI_WDATA,
  input wire [(C_DATA_WIDTH/8)-1 : 0] S_AXI_WSTRB,
  input wire                          S_AXI_WVALID,
  output wire                         S_AXI_WREADY,
  //Write response channel
  output wire [1 : 0]                 S_AXI_BRESP,
  output wire                         S_AXI_BVALID,
  input wire                          S_AXI_BREADY,
  //Read address channel
  input wire [C_ADDR_WIDTH-1 : 0]     S_AXI_ARADDR,
  input wire [2 : 0]                  S_AXI_ARPROT,
  input wire                          S_AXI_ARVALID,
  output wire                         S_AXI_ARREADY,
  //Read data channel
  output wire [C_DATA_WIDTH-1 : 0]    S_AXI_RDATA,
  output wire [1 : 0]                 S_AXI_RRESP,
  output wire                         S_AXI_RVALID,
  input wire                          S_AXI_RREADY
);
"""

