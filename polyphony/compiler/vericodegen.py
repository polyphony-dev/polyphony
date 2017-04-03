from .verilog_common import pyop2verilogop, is_verilog_keyword
from .ir import Ctx
from .signal import Signal
from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .env import env
from .hdlinterface import *
from .memref import One2NMemNode, N2OneMemNode
from logging import getLogger
logger = getLogger(__name__)


class VerilogCodeGen(AHDLVisitor):
    def __init__(self, scope):
        self.codes = []
        self.indent = 0
        self.scope = scope
        self.module_info = self.scope.module_info

    def result(self):
        return ''.join(self.codes)

    def emit(self, code, with_indent=True, newline=True):
        if with_indent:
            self.codes.append((' ' * self.indent) + code)
        else:
            self.codes.append(code)
        if newline:
            self.codes.append('\n')

    def tab(self):
        return ' ' * self.indent

    def set_indent(self, val):
        self.indent += val

    def generate(self):
        """Output verilog module format:

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

        for stm in sorted(fsm.reset_stms, key=lambda s: str(s)):
            if stm.dst.is_a(AHDL_VAR) and stm.dst.sig.is_net():
                continue
            self.visit(stm)
        if not fsm.stgs:
            self.set_indent(-2)
            self.emit('end')  # end if (READY)
            self.set_indent(-2)
            self.emit('end')
            self.emit('')
            return
        for stg in fsm.stgs:
            if stg.is_main():
                main_stg = stg
        assert main_stg

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
        self.emit('end')  # end if (READY)
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
        self._generate_edge_detector()
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
        if self.scope.is_module() or self.scope.is_function_module():
            ports.append('input wire clk')
            ports.append('input wire rst')
        for interface in self.module_info.interfaces.values():
            ports.extend(self._get_io_names_from(interface))
        self.emit((',\n' + self.tab()).join(ports))

    def _generate_signal(self, sig):
        sign = 'signed' if sig.is_int() else ''
        return '{:<6} [{}:0] {}'.format(sign, sig.width - 1, sig.name)

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
            for tag, nets in self.module_info.get_net_decls(with_array=False):
                for net in nets:
                    if net.sig.is_onehot():
                        self.emit(
                            '$display("%8d:WIRE  :{}      {} = 0b%b", $time, {});'.
                            format(self.scope.orig_name, net.sig, net.sig))
                    else:
                        self.emit(
                            '$display("%8d:WIRE  :{}      {} = 0x%2h (%1d)", $time, {}, {});'.
                            format(self.scope.orig_name, net.sig, net.sig, net.sig))
            self.emit('end')
            self.emit('end')
            self.emit('')

        self.emit('')

    def _generate_decls(self):
        for tag, decls in sorted(self.module_info.decls.items(), key=lambda t: str(t)):
            decls = [decl for decl in decls if isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit('//signals: {}'.format(tag))
                for decl in sorted(decls, key=lambda d: str(d)):
                    self.visit(decl)
        for tag, decls in sorted(self.module_info.decls.items()):
            decls = [decl for decl in decls if not isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit('//combinations: {}'.format(tag))
                for decl in sorted(decls, key=lambda d: str(d)):
                    self.visit(decl)

    def _get_io_names_from(self, interface):
        in_names = []
        out_names = []
        for port in interface.regs():
            if port.dir == 'in':
                assert False
            else:
                io_name = self._to_io_name(port.width, 'reg', 'output', port.signed,
                                           interface.port_name(port))
                out_names.append(io_name)
        for port in interface.nets():
            if port.dir == 'in':
                io_name = self._to_io_name(port.width, 'wire', 'input', port.signed,
                                           interface.port_name(port))
                in_names.append(io_name)
            else:
                io_name = self._to_io_name(port.width, 'wire', 'output', port.signed,
                                           interface.port_name(port))
                out_names.append(io_name)
        return in_names + out_names

    def _to_io_name(self, width, typ, io, signed, port_name):
        if width == 1:
            ioname = '{} {} {}'.format(io, typ, port_name)
        else:
            if signed:
                ioname = '{} {} signed [{}:0] {}'.format(io,
                                                         typ, width - 1,
                                                         port_name)
            else:
                ioname = '{} {} [{}:0] {}'.format(io,
                                                  typ,
                                                  width - 1,
                                                  port_name)
        return ioname

    def _to_sub_module_connect(self, instance_name, inf, acc, port):
        port_name = inf.port_name(port)
        accessor_name = acc.port_name(port)
        connection = '.{}({})'.format(port_name, accessor_name)
        return connection

    def _generate_sub_module_instances(self):
        if not self.module_info.sub_modules:
            return
        self.emit('//sub modules')
        for name, info, connections, param_map in sorted(self.module_info.sub_modules.values(),
                                                         key=lambda n: str(n)):
            ports = []
            ports.append('.clk(clk)')
            ports.append('.rst(rst)')
            for inf, acc in sorted(connections, key=lambda c: str(c)):
                for p in inf.ports.all():
                    ports.append(self._to_sub_module_connect(name, inf, acc, p))

            self.emit('//{} instance'.format(name))
            #for port, signal in port_map.items():
            #    ports.append('.{}({})'.format(port, signal))
            if param_map:
                params = []
                for param_name, value in param_map.items():
                    params.append('.{}({})'.format(param_name, value))

                self.emit('{}#('.format(info.qualified_name))
                self.set_indent(2)
                self.emit('{}'.format((',\n' + self.tab()).join(params)))
                self.emit(')')
                self.emit('{}('.format(name))
                self.set_indent(2)
                self.emit('{}'.format((',\n' + self.tab()).join(ports)))
                self.set_indent(-2)
                self.emit(');')
                self.set_indent(-2)
            else:
                self.emit('{} {}('.format(info.qualified_name, name))
                self.set_indent(2)
                self.emit('{}'.format((',\n' + self.tab()).join(ports)))
                self.set_indent(-2)
                self.emit(');')
        self.emit('')

    def _generate_edge_detector(self):
        if not self.module_info.edge_detectors:
            return
        regs = set([sig for sig, _, _ in self.module_info.edge_detectors])
        self.emit('//edge detectors')
        for sig in regs:
            delayed_name = '{}_d'.format(sig.name)
            self.emit('reg {};'.format(delayed_name))
            self.emit('always @(posedge clk) {} <= {};'.format(delayed_name, sig.name))
            #self.set_indent(2)
            #self.emit()
            #self.set_indent(-2)
            #self.emit('end')
            #self.emit('')

        detect_var_names = set()
        for sig, old, new in self.module_info.edge_detectors:
            delayed_name = '{}_d'.format(sig.name)
            detect_var_name = 'is_{}_change_{}_to_{}'.format(sig.name, old, new)
            if detect_var_name in detect_var_names:
                continue
            detect_var_names.add(detect_var_name)
            self.emit('wire {};'.format(detect_var_name))
            self.emit('assign {} = ({}=={} && {}=={});'.
                      format(detect_var_name,
                             delayed_name,
                             old,
                             sig.name,
                             new))

    def _process_State(self, state):
        self.current_state = state
        code = '{0}: begin'.format(state.name)
        self.emit(code)
        self.set_indent(2)
        if env.hdl_debug_mode:
            self.emit('$display("%8d:STATE:{}  {}", $time);'.
                      format(self.scope.orig_name,
                             state.name))

        for code in state.codes:
            self.visit(code)

        self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_CONST(self, ahdl):
        if ahdl.value is None:
            return "'bx"
        elif isinstance(ahdl.value, bool):
            return str(int(ahdl.value))
        elif isinstance(ahdl.value, str):
            return '"' + ahdl.value + '"'
        return str(ahdl.value)

    def visit_AHDL_VAR(self, ahdl):
        if is_verilog_keyword(ahdl.sig.name):
            return ahdl.sig.name + '_'
        return ahdl.sig.name

    def visit_AHDL_MEMVAR(self, ahdl):
        if is_verilog_keyword(ahdl.sig.name):
            return ahdl.sig.name + '_'
        return ahdl.sig.name

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        return '{}[{}]'.format(self.visit(ahdl.memvar), self.visit(ahdl.offset))

    def visit_AHDL_SYMBOL(self, ahdl):
        if is_verilog_keyword(ahdl.name):
            return ahdl.name + '_'
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
        if len(ahdl.args) > 1:
            op = ' ' + pyop2verilogop(ahdl.op) + ' '
            return '({})'.format(op.join([self.visit(a) for a in ahdl.args]))
        else:
            exp = self.visit(ahdl.args[0])
            return '{}{}'.format(pyop2verilogop(ahdl.op), exp)

    def visit_AHDL_NOP(self, ahdl):
        if isinstance(ahdl.info, AHDL):
            self.emit('/*')
            self.visit(ahdl.info)
            self.emit('*/')
        else:
            self.emit('/*' + str(ahdl.info) + '*/')

    def visit_AHDL_INLINE(self, ahdl):
        self.emit(ahdl.code + ';')

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR) and (ahdl.dst.sig.is_condition() or ahdl.dst.sig.is_net()):
            self.module_info.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
            self.emit('/* {} <= {}; */'.format(self.visit(ahdl.dst), self.visit(ahdl.src)))
        elif ahdl.dst.is_a(AHDL_MEMVAR) and ahdl.src.is_a(AHDL_MEMVAR):
            assert False
        else:
            src = self.visit(ahdl.src)
            dst = self.visit(ahdl.dst)
            if env.hdl_debug_mode:
                self.emit('$display("%8d:REG  :{}      {} <= 0x%2h (%1d)", $time, {}, {});'.
                          format(self.scope.orig_name, dst, src, src))
            self.emit('{} <= {};'.format(dst, src))

    def visit_AHDL_MEM(self, ahdl):
        name = ahdl.name.hdl_name()
        offset = self.visit(ahdl.offset)
        return '{}[{}]'.format(name, offset)

    def visit_AHDL_IF(self, ahdl):
        cond0 = self.visit(ahdl.conds[0])
        if cond0[0] != '(':
            cond0 = '(' + cond0 + ')'
        self.emit('if {} begin'.format(cond0))
        self.set_indent(2)
        for code in ahdl.codes_list[0]:
            self.visit(code)
        self.set_indent(-2)
        for cond, codes in zip(ahdl.conds[1:], ahdl.codes_list[1:]):
            if cond and not (cond.is_a(AHDL_CONST) and cond.value == 1):
                cond = self.visit(cond)
                if cond[0] != '(':
                    cond = '(' + cond + ')'
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

    def visit_AHDL_FUNCALL(self, ahdl):
        return '{}({})'.format(self.visit(ahdl.name), ', '.join([self.visit(arg) for arg in ahdl.args]))

    def visit_AHDL_PROCCALL(self, ahdl):
        args = []
        for arg in ahdl.args:
            a = self.visit(arg)
            args.append(a)

        if ahdl.name == '!hdl_print':
            fmts = ['%s' if a[0] == '"' else '%1d' for a in args]
            self.emit('$display("{}", {});'.format(' '.join(fmts), ', '.join(args)))
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

    def visit_AHDL_SIGNAL_DECL(self, ahdl):
        nettype = 'reg' if ahdl.sig.is_reg() else 'wire'
        if ahdl.sig.width == 1:
            self.emit('{} {};'.format(nettype, ahdl.sig.name))
        else:
            self.emit('{} {};'.format(nettype, self._generate_signal(ahdl.sig)))

    def visit_AHDL_SIGNAL_ARRAY_DECL(self, ahdl):
        nettype = 'reg' if ahdl.sig.is_regarray() else 'wire'
        if ahdl.sig.width == 1:
            self.emit('{} {}[0:{}];'.format(nettype,
                                            ahdl.sig.name,
                                            ahdl.size - 1))
        else:
            sign = 'signed' if ahdl.sig.is_int() else ''
            self.emit('{} {:<6} [{}:0] {} [0:{}];'.format(nettype,
                                                          sign,
                                                          ahdl.sig.width - 1,
                                                          ahdl.sig.name,
                                                          ahdl.size - 1))

    def visit_AHDL_ASSIGN(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('assign {} = {};'.format(dst, src))

    def visit_AHDL_CONNECT(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('{} = {};'.format(dst, src))

    def visit_MEM_SWITCH(self, ahdl):
        prefix = ahdl.args[0]
        dst_node = ahdl.args[1]
        src_node = ahdl.args[2]
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
        self.visit(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE),
                             AHDL_SYMBOL('\'b' + one_hot_mask)))

    def visit_AHDL_META(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_WAIT_EDGE(self, ahdl):
        old, new = ahdl.args[0], ahdl.args[1]
        detect_vars = []
        for var in ahdl.args[2:]:
            detect_var_name = 'is_{}_change_{}_to_{}'.format(var.sig.name,
                                                             self.visit(old),
                                                             self.visit(new))
            detect_vars.append(AHDL_SYMBOL(detect_var_name))
        if len(detect_vars) > 1:
            conds = [AHDL_OP('And', *detect_vars)]
        else:
            conds = [detect_vars[0]]
        if ahdl.codes:
            codes = ahdl.codes[:]
        else:
            codes = []
        if ahdl.transition:
            codes.append(ahdl.transition)
        ahdl_if = AHDL_IF(conds, [codes])
        self.visit(ahdl_if)

    def visit_WAIT_VALUE(self, ahdl):
        value = ahdl.args[0]
        detect_exps = [AHDL_OP('Eq', var, value) for var in ahdl.args[1:]]
        if len(detect_exps) > 1:
            conds = [AHDL_OP('And', *detect_exps)]
        else:
            conds = [detect_exps[0]]
        if ahdl.codes:
            codes = ahdl.codes[:]
        else:
            codes = []
        if ahdl.transition:
            codes.append(ahdl.transition)
        ahdl_if = AHDL_IF(conds, [codes])
        self.visit(ahdl_if)

    def visit_AHDL_META_WAIT(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_AHDL_FUNCTION(self, ahdl):
        self.emit('function [{}:0] {} ('.format(ahdl.output.sig.width - 1,
                                                self.visit(ahdl.output)))
        self.set_indent(2)
        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}'.format(input.sig.width - 1, self.visit(input)))
            else:
                self.emit('input [{}:0] {},'.format(input.sig.width - 1, self.visit(input)))
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
        self.emit('function [{}:0] {} ('.format(ahdl.output.width - 1, ahdl.name))
        self.set_indent(2)
        self.emit('input [{}:0] {},'.format(ahdl.selector.sig.width - 1, self.visit(ahdl.selector)))

        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}'.format(input.width - 1, input.name))
            else:
                self.emit('input [{}:0] {},'.format(input.width - 1, input.name))

        self.set_indent(-2)
        self.emit(');')
        self.emit('begin')
        self.set_indent(2)

        self.emit('case (1\'b1)')
        self.set_indent(2)
        for i, input in enumerate(ahdl.inputs):
            self.emit("{}[{}]: {} = {};".format(ahdl.selector.sig.name,
                                                i,
                                                ahdl.name,
                                                input.name))
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
                    input_name = ahdl.input.name
                    input_width = ahdl.input.width
                elif isinstance(ahdl.input, int):
                    input_name = ahdl.input
                    input_width = ahdl.width
                self.emit('assign {} = 1\'b1 == {}[{}] ? {}:{}\'bz;'
                          .format(output.name,
                                  ahdl.selector.sig.name,
                                  i,
                                  input_name,
                                  input_width))
        else:
            self.emit('assign {} = {};'.format(ahdl.outputs[0].name, ahdl.input.name))

    def visit_AHDL_TRANSITION(self, ahdl):
        state_var = AHDL_SYMBOL(self.current_state_sig.name)
        state = AHDL_SYMBOL(ahdl.target.name)
        self.visit(AHDL_MOVE(state_var, state))

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)
