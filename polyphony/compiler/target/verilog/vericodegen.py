import os
from .verilog_common import pyop2verilogop, is_verilog_keyword
from ...ahdl.ahdl import *
from ...ahdl.ahdlvisitor import AHDLVisitor
from ...common.common import get_src_text
from ...common.env import env
from logging import getLogger
logger = getLogger(__name__)


class VerilogCodeGen(AHDLVisitor):
    def __init__(self, hdlmodule):
        self.codes = []
        self.indent = 0
        self.hdlmodule = hdlmodule

    def result(self):
        return ''.join(self.codes)

    def emit(self, code, with_indent=True, newline=True, continueus=False):
        if continueus:
            prev_code = self.codes[-1]
            if prev_code[-1] == '\n':
                self.codes[-1] = prev_code[:-1]
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
        self._generate_include()
        self._generate_module()
        self.emit('endmodule\n')

    def _generate_include(self):
        pass

    def _generate_module(self):
        self._generate_module_header()
        self.set_indent(2)
        self._generate_localparams()
        self._generate_decls()
        self._generate_sub_module_instances()
        self._generate_net_monitor()
        for task in self.hdlmodule.tasks:
            self.visit(task)
        self.set_indent(-2)

    def _generate_module_header(self):
        self.emit(f'module {self.hdlmodule.qualified_name}')
        if self.hdlmodule.parameters:
            self.set_indent(2)
            self.emit('#(')
            self.set_indent(2)
            self._generate_parameter_decls(self.hdlmodule.parameters)
            self.set_indent(-2)
            self.emit(')')
            self.set_indent(-2)
        self.set_indent(2)
        self.emit('(')
        self.set_indent(2)

        self._generate_io_port()
        self.set_indent(-2)
        self.emit(');')
        self.set_indent(-2)
        self.emit('')

    def _generate_parameter_decls(self, parameters):
        params = []
        for sig, val in parameters:
            if sig.is_int():
                params.append(f'parameter signed [{sig.width-1}:0] {sig.name} = {val}')
            else:
                params.append(f'parameter [{sig.width-1}:0] {sig.name} = {val}')
        self.emit((',\n' + self.tab()).join(params))

    def _generate_io_port(self):
        ports = []
        if self.hdlmodule.scope.is_module() or self.hdlmodule.scope.is_function_module():
            ports.append('input wire clk')
            ports.append('input wire rst')
        for var in self.hdlmodule.inputs():
            typ = 'reg' if var.sig.is_reg() else 'wire'
            signed = 'signed' if var.sig.is_int() else ''
            width = f'[{var.sig.width-1}:0]' if var.sig.width > 1 else ''
            name = self._safe_name(var.hdl_name)
            ports.append(f'input  {typ:4s} {signed:6s} {width:8s} {name}')
        for var in self.hdlmodule.outputs():
            typ = 'wire' if var.sig.is_net() else 'reg'
            signed = 'signed' if var.sig.is_int() else ''
            width = f'[{var.sig.width-1}:0]' if var.sig.width > 1 else ''
            name = self._safe_name(var.hdl_name)
            if var.sig.is_initializable():
                ports.append(f'output {typ:4s} {signed:6s} {width:8s} {name} = {var.sig.init_value}')
            else:
                ports.append(f'output {typ:4s} {signed:6s} {width:8s} {name}')
        self.emit((',\n' + self.tab()).join(ports))

    def _generate_signal(self, sig):
        name = self._safe_name(sig.name)
        if sig.is_regarray() or sig.is_netarray():
            width = sig.width[0]
            size = sig.width[1]
            if width == 1:
                return f'{name}[0:{size}-1]'
            else:
                sign = 'signed' if sig.is_int() else ''
                return f'{sign:<6} [{width-1}:0] {name} [0:{size}-1]'
        else:
            if sig.width == 1:
                return name
            else:
                sign = 'signed' if sig.is_int() else ''
                return f'{sign:<6} [{sig.width-1}:0] {name}'

    def _generate_localparams(self):
        if not self.hdlmodule.constants:
            return
        self.emit('//localparams')
        for sig, val in sorted(self.hdlmodule.constants.items(), key=lambda item: item[0].name):
            self.emit(f'localparam {sig.name} = {val};')
        self.emit('')

    def _generate_net_monitor(self):
        if env.hdl_debug_mode and not self.hdlmodule.scope.is_testbench():
            self.emit('always @(posedge clk) begin')
            self.emit(f'if (rst==0 && {self.current_state_sig.name}!=0) begin')
            for net in self.hdlmodule.get_signals({'net'}, {'input', 'output'}):
                self.emit(f'$display("%8d:WIRE  :{self.hdlmodule.name:<10}', newline=False)
                if net.sig.is_onehot():
                    self.emit(f'{net.sig.name} = 0b%b", $time, {net.sig.name});')
                else:
                    self.emit(f'{net.sig.name} = 0x%2h (%1d)", $time, {net.sig.name}, {net.sig.name});')
            self.emit('end')
            self.emit('end')
            self.emit('')

        self.emit('')

    def _generate_decls(self):
        self.emit(f'//signals')
        for reg in self.hdlmodule.get_signals({'reg', 'regarray'}, {'input', 'output'}):
            self.emit(f'reg {self._generate_signal(reg)};')
        for net in self.hdlmodule.get_signals({'net', 'netarray'}, {'input', 'output'}):
            self.emit(f'wire {self._generate_signal(net)};')

        for tag, decls in sorted(self.hdlmodule.decls.items()):
            if decls:
                self.emit(f'//combinations: {tag}')
                for decl in sorted(decls, key=lambda d: d.name):
                    self.visit(decl)
        for func in self.hdlmodule.functions:
            self.visit(func)

    def _generate_sub_module_instances(self):
        if not self.hdlmodule.sub_modules:
            return
        self.emit('//sub modules')
        for name, sub_module, connections, param_map in sorted(self.hdlmodule.sub_modules.values(),
                                                               key=lambda n: str(n)):
            ports = []
            ports.append('.clk(clk)')
            ports.append('.rst(rst)')
            for var, acc in connections:
                ports.append(f'.{var.hdl_name}({acc.name})')

            self.emit(f'//{name} instance')
            if param_map:
                params = []
                for param_name, value in param_map.items():
                    params.append(f'.{param_name}({value})')

                self.emit(f'{sub_module.qualified_name}#(')
                self.set_indent(2)
                self.emit((',\n' + self.tab()).join(params))
                self.emit(')')
                self.emit(f'{name}(')
                self.set_indent(2)
                self.emit((',\n' + self.tab()).join(ports))
                self.set_indent(-2)
                self.emit(');')
                self.set_indent(-2)
            else:
                self.emit(f'{sub_module.qualified_name} {name}(')
                self.set_indent(2)
                self.emit((',\n' + self.tab()).join(ports))
                self.set_indent(-2)
                self.emit(');')
        self.emit('')

    def _process_State(self, state):
        assert False

    def visit_State(self, state):
        assert False

    def visit_PipelineStage(self, stage):
        self.emit(f'/*** {stage.name} ***/')
        self.visit(stage.block)
        self.emit('')

    def visit_AHDL_CONST(self, ahdl):
        if ahdl.value is None:
            return "'bx"
        elif isinstance(ahdl.value, bool):
            return str(int(ahdl.value))
        elif isinstance(ahdl.value, str):
            s = repr(ahdl.value)
            return '"' + s[1:-1] + '"'
        return str(ahdl.value)

    def _safe_name(self, name):
        if is_verilog_keyword(name):
            return name + '_'
        name = name.replace('#', '_')
        if name[0].isnumeric():
            return '_' + name
        return name

    def visit_AHDL_VAR(self, ahdl):
        return self._safe_name(ahdl.hdl_name)

    def visit_AHDL_MEMVAR(self, ahdl):
        return self._safe_name(ahdl.hdl_name)

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        return f'{self.visit(ahdl.memvar)}[{self.visit(ahdl.offset)}]'

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
            return f'({op.join([self.visit(a) for a in ahdl.args])})'
        elif ahdl.is_unop():
            exp = self.visit(ahdl.args[0])
            return f'{pyop2verilogop(ahdl.op)}{exp}'
        else:
            exp = self.visit(ahdl.args[0])
            return f'{exp}'

    def visit_AHDL_META_OP(self, ahdl):
        assert False

    def visit_AHDL_SLICE(self, ahdl):
        v = self.visit(ahdl.var)
        hi = self.visit(ahdl.hi)
        lo = self.visit(ahdl.lo)
        return f'{v}[{hi}:{lo}]'

    def visit_AHDL_NOP(self, ahdl):
        if isinstance(ahdl.info, AHDL):
            self.emit(f'/*{self.visit(ahdl.info)}*/')
        else:
            self.emit(f'/*{str(ahdl.info)}*/')

    def visit_AHDL_INLINE(self, ahdl):
        self.emit(ahdl.code)

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR) and ahdl.dst.sig.is_net():
            assert False
        elif ahdl.dst.is_a(AHDL_SUBSCRIPT) and ahdl.dst.memvar.sig.is_netarray():
            assert False
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        if env.hdl_debug_mode:
            self.emit(f'$display("%8d:REG  :{self.hdlmodule.name:<10}', newline=False)
            self.emit(f'{dst} <= 0x%2h (%1d)", $time, {src}, {src});')
        self.emit(f'{dst} <= {src};')

    def visit_AHDL_IF(self, ahdl):
        blocks = 0
        for i, (cond, ahdlblk) in enumerate(zip(ahdl.conds, ahdl.blocks)):
            blocks += 1
            if cond and not (cond.is_a(AHDL_CONST) and cond.value == 1) or i == 0:
                cond = self.visit(cond)
                if cond[0] != '(':
                    cond = '(' + cond + ')'
                if i == 0:
                    self.emit(f'if {cond} begin')
                else:
                    self.emit(f'end else if {cond} begin')
                self.set_indent(2)
                for code in ahdlblk.codes:
                    self.visit(code)
                self.set_indent(-2)
            else:
                self.emit('end else begin')
                self.set_indent(2)
                for code in ahdlblk.codes:
                    self.visit(code)
                self.set_indent(-2)
        if blocks:
            self.emit('end')

    def visit_AHDL_IF_EXP(self, ahdl):
        cond = self.visit(ahdl.cond)
        lexp = self.visit(ahdl.lexp)
        rexp = self.visit(ahdl.rexp)
        return f'({cond} ? {lexp} : {rexp})'

    def visit_AHDL_FUNCALL(self, ahdl):
        name = self.visit(ahdl.name)
        args = ', '.join([self.visit(arg) for arg in ahdl.args])
        return f'{name}({args})'

    def visit_AHDL_PROCCALL(self, ahdl):
        args = [self.visit(arg) for arg in ahdl.args]
        if ahdl.name == '!hdl_print':
            fmts = ' '.join(['%s' if a[0] == '"' else '%1d' for a in args])
            args = ', '.join(args)
            self.emit(f'$display("{fmts}", {args});')
        elif ahdl.name == '!hdl_verilog_display':
            args = ', '.join(args)
            self.emit(f'$display({args});')
        elif ahdl.name == '!hdl_verilog_write':
            args = ', '.join(args)
            self.emit(f'$write({args});')
        elif ahdl.name == '!hdl_assert':
            #expand condtion expression for the assert message
            exp = ahdl.args[0]
            exp_str = args[0]
            if exp.is_a(AHDL_VAR) and exp.sig.is_condition():
                for tag, assign in self.hdlmodule.get_static_assignment():
                    if assign.dst.is_a(AHDL_VAR) and assign.dst.sig == exp.sig:
                        remove_assign = (tag, assign)
                        exp_str = self.visit(assign.src)
                        self.hdlmodule.remove_decl(*remove_assign)
                        break
            exp_str = exp_str.replace('==', '===').replace('!=', '!==')
            self.emit(f'if (!{exp_str}) begin')
            src_text = self._get_source_text(ahdl)
            if src_text:
                self.emit(f'  $display("ASSERTION FAILED: {src_text}"); $finish;')
            else:
                self.emit(f'  $display("ASSERTION FAILED: {exp_str}"); $finish;')
            self.emit('end')
        else:
            args = ', '.join(args)
            self.emit(f'{ahdl.name}({args});')

    def visit_AHDL_ASSIGN(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit(f'assign {dst} = {src};')

    def visit_AHDL_EVENT_TASK(self, ahdl):
        evs = []
        for v, e in ahdl.events:
            if e == 'rising':
                ev = 'posedge '
            elif e == 'falling':
                ev = 'negedge '
            else:
                ev = ''
            evs.append(f'{ev}{v.name}')
        events = ', '.join(evs)
        self.emit(f'always @({events}) begin')
        self.set_indent(2)
        self.visit(ahdl.stm)
        self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_CONNECT(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit(f'{dst} = {src};')

    def visit_AHDL_META(self, ahdl):
        assert False

    def visit_AHDL_META_WAIT(self, ahdl):
        assert False

    def visit_AHDL_FUNCTION(self, ahdl):
        if ahdl.output.sig.is_rom():
            width = ahdl.output.sig.width[0]
        else:
            width = ahdl.output.sig.width
        self.emit(f'function [{width-1}:0] {self.visit(ahdl.output)} (')
        self.set_indent(2)
        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit(f'input [{input.sig.width-1}:0] {self.visit(input)}')
            else:
                self.emit(f'input [{input.sig.width-1}:0] {self.visit(input)},')
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
        self.emit(f'case ({self.visit(ahdl.sel)})')
        self.set_indent(2)
        for item in ahdl.items:
            self.visit(item)
        self.set_indent(-2)
        self.emit('endcase')

    def visit_AHDL_CASE_ITEM(self, ahdl):
        self.emit(f'{self.visit(ahdl.val)}: begin')
        self.set_indent(2)
        self.visit(ahdl.block)
        self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_TRANSITION(self, ahdl):
        assert False

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_BLOCK(self, ahdl):
        for c in ahdl.codes:
            self.visit(c)

    def visit(self, ahdl):
        if ahdl.is_a(AHDL_STM):
            self.current_stm = ahdl
        visitor = self.find_visitor(ahdl.__class__)
        ret = visitor(ahdl)
        if env.dev_debug_mode and id(ahdl) in self.hdlmodule.ahdl2dfgnode:
            self._emit_source_text(ahdl)
        return ret

    def _get_source_text(self, ahdl):
        _, node = self.hdlmodule.ahdl2dfgnode[id(ahdl)]
        if node.tag.loc.lineno < 1:
            return
        text = get_src_text(node.tag.loc.filename, node.tag.loc.lineno)
        text = text.strip()
        if not text:
            return
        if text[-1] == '\n':
            text = text[:-1]
        filename = os.path.basename(node.tag.loc.filename)
        return f'{filename}:{node.tag.loc.lineno} {text}'

    def _emit_source_text(self, ahdl):
        text = self._get_source_text(ahdl)
        if text:
            self.emit(f'/* {text} */', continueus=True)
