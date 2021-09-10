﻿import functools
import os
from .verilog_common import pyop2verilogop, is_verilog_keyword
from ...ahdl.ahdl import *
from ...ahdl.ahdlvisitor import AHDLVisitor
from ...ahdl.hdlinterface import *
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

        self.set_indent(2)
        for fsm in self.hdlmodule.fsms.values():
            self._generate_process(fsm)
        self.set_indent(-2)
        main_code = self.result()
        self.codes = []

        self._generate_include()
        self._generate_module()
        self.emit(main_code)
        self.emit('endmodule\n')

    def _generate_process(self, fsm):
        self._add_state_constants(fsm)
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
        self.emit(f'{self.current_state_sig.name} <= {main_stg.states[0].name};')
        self.set_indent(-2)
        self.emit('end else begin //if (rst)')
        self.set_indent(2)

        self.emit(f'case({self.current_state_sig.name})')

        for stg in sorted(fsm.stgs, key=lambda s: s.name):
            for i, state in enumerate(stg.states):
                self._process_State(state)

        self.emit('endcase')
        self.set_indent(-2)
        self.emit('end')  # end if (READY)
        self.set_indent(-2)
        self.emit('end')
        self.emit('')

    def _add_state_constants(self, fsm):
        i = 0
        for stg in fsm.stgs:
            for state in stg.states:
                self.hdlmodule.add_state_constant(state.name, i)
                i += 1
        fsm.state_var.width = i.bit_length()

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
        self._generate_clock_counter()
        self._generate_net_monitor()
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
        for interface in self.hdlmodule.interfaces.values():
            ports.extend(self._get_io_names_from(interface))
        self.emit((',\n' + self.tab()).join(ports))

    def _generate_signal(self, sig):
        name = self._safe_name(sig)
        if sig.width == 1:
            return name
        else:
            sign = 'signed' if sig.is_int() else ''
            return f'{sign:<6} [{sig.width-1}:0] {name}'

    def _generate_localparams(self):
        constants = self.hdlmodule.constants + self.hdlmodule.state_constants
        if not constants:
            return
        self.emit('//localparams')
        for name, val in constants:
            self.emit(f'localparam {name} = {val};')
        self.emit('')

    def _generate_net_monitor(self):
        if env.hdl_debug_mode and not self.hdlmodule.scope.is_testbench():
            self.emit('always @(posedge clk) begin')
            self.emit(f'if (rst==0 && {self.current_state_sig.name}!=0) begin')
            for tag, nets in self.hdlmodule.get_net_decls(with_array=False):
                for net in nets:
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
        for tag, decls in sorted(self.hdlmodule.decls.items(), key=lambda t: str(t)):
            decls = [decl for decl in decls if isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit(f'//signals: {tag}')
                for decl in sorted(decls, key=lambda d: d.name):
                    self.visit(decl)
        for tag, decls in sorted(self.hdlmodule.decls.items()):
            decls = [decl for decl in decls if not isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit(f'//combinations: {tag}')
                for decl in sorted(decls, key=lambda d: d.name):
                    self.visit(decl)

    def _get_io_names_from(self, interface):
        in_names = []
        out_names = []
        for port in interface.regs():
            if port.dir == 'in':
                assert False
            else:
                # WORKAROUND
                if isinstance(interface, SingleWriteInterface):
                    net_typ = 'wire' if interface.signal and not interface.signal.is_reg() else 'reg'
                else:
                    net_typ = 'reg'
                io_name = self._to_io_name(port.width, net_typ, 'output', port.signed,
                                           interface.port_name(port))
                if (isinstance(interface, SinglePortInterface) and
                        interface.signal.is_initializable()):
                    io_name += f' = {int(interface.signal.init_value)}'
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
        if is_verilog_keyword(port_name):
            port_name = port_name + '_'
        if width == 1:
            ioname = f'{io} {typ} {port_name}'
        else:
            if signed:
                ioname = f'{io} {typ} signed [{width-1}:0] {port_name}'
            else:
                ioname = f'{io} {typ} [{width-1}:0] {port_name}'
        return ioname

    def _to_sub_module_connect(self, instance_name, inf, acc, port):
        port_name = inf.port_name(port)
        if is_verilog_keyword(port_name):
            port_name = port_name + '_'
        accessor_name = acc.port_name(port)
        connection = f'.{port_name}({accessor_name})'
        return connection

    def _to_sub_module_connect_default(self, instance_name, inf, port):
        port_name = inf.port_name(port)
        if is_verilog_keyword(port_name):
            port_name = port_name + '_'
        connection = f'.{port_name}({port.width}\'d{port.default})'
        return connection

    def _generate_sub_module_instances(self):
        if not self.hdlmodule.sub_modules:
            return
        self.emit('//sub modules')
        for name, sub_module, connections, param_map in sorted(self.hdlmodule.sub_modules.values(),
                                                               key=lambda n: str(n)):
            ports = []
            ports.append('.clk(clk)')
            ports.append('.rst(rst)')
            conns = connections['']
            for inf, acc in sorted(conns, key=lambda c: str(c)):
                if acc.connected:
                    for p in inf.ports:
                        ports.append(self._to_sub_module_connect(name, inf, acc, p))
                else:
                    for p in inf.ports:
                        if p.dir == 'in':
                            ports.append(self._to_sub_module_connect_default(name, inf, p))
                        else:
                            pass
            conns = connections['ret']
            for inf, acc in sorted(conns, key=lambda c: str(c)):
                if acc.connected:
                    for p in inf.ports:
                        ports.append(self._to_sub_module_connect(name, inf, acc, p))
                else:
                    for p in inf.ports:
                        if p.dir == 'in':
                            ports.append(self._to_sub_module_connect_default(name, inf, p))
                        else:
                            pass
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

    def _generate_edge_detector(self):
        if not self.hdlmodule.edge_detectors:
            return
        regs = set([sig for sig, _, _ in self.hdlmodule.edge_detectors])
        self.emit('//edge detectors')
        for sig in regs:
            delayed_name = f'{sig.name}_d'
            self.emit(f'reg {delayed_name};')
            self.emit(f'always @(posedge clk) {delayed_name} <= {sig.name};')
            #self.set_indent(2)
            #self.emit()
            #self.set_indent(-2)
            #self.emit('end')
            #self.emit('')

        detect_var_names = set()
        for sig, old, new in self.hdlmodule.edge_detectors:
            delayed_name = f'{sig.name}_d'
            detect_var_name = f'is_{sig.name}_change_{old}_to_{new}'
            if detect_var_name in detect_var_names:
                continue
            detect_var_names.add(detect_var_name)
            self.emit(f'wire {detect_var_name};')
            self.emit(f'assign {detect_var_name} = ({delayed_name}=={old} && {sig.name}=={new});')

    def _generate_clock_counter(self):
        if not self.hdlmodule.clock_signal:
            return
        name = self.hdlmodule.clock_signal.name
        width = self.hdlmodule.clock_signal.width
        self.emit('//clock counter')
        self.emit(f'reg [{width-1}:0] {name};')
        self.emit(f'always @(posedge clk) if (rst) {name} <= 0; else {name} <= {name} + 1;')

    def _process_State(self, state):
        self.current_state = state
        code = f'{state.name}: begin'
        self.emit(code)
        self.set_indent(2)
        if env.hdl_debug_mode:
            self.emit(f'$display("%8d:STATE:{self.hdlmodule.name}  {state.name}", $time);')
        self.visit_State(state)

        self.set_indent(-2)
        self.emit('end')

    def visit_State(self, state):
        for code in state.codes:
            self.visit(code)

    def visit_PipelineStage(self, stage):
        self.emit(f'/*** {stage.name} ***/')
        if stage.enable:
            self.visit(stage.enable)
        for code in stage.codes:
            self.visit(code)
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

    def _safe_name(self, sig):
        if sig.is_reserved():
            return sig.name
        if is_verilog_keyword(sig.name):
            return sig.name + '_'
        return sig.name

    def visit_AHDL_VAR(self, ahdl):
        return self._safe_name(ahdl.sig)

    def visit_AHDL_MEMVAR(self, ahdl):
        return self._safe_name(ahdl.sig)

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
        ahdl.op
        method = 'visit_AHDL_META_OP_' + ahdl.op
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_AHDL_META_OP_edge(self, ahdl):
        old, new = ahdl.args[0], ahdl.args[1]
        detect_vars = []
        for var in ahdl.args[2:]:
            detect_var_name = f'is_{var.sig.name}_change_{self.visit(old)}_to_{self.visit(new)}'
            detect_vars.append(AHDL_SYMBOL(detect_var_name))
        if len(detect_vars) > 1:
            return self.visit(AHDL_OP('And', *detect_vars))
        else:
            return self.visit(detect_vars[0])

    def visit_AHDL_META_OP_cond(self, ahdl):
        eqs = []
        for i in range(0, len(ahdl.args), 3):
            cond  = ahdl.args[i]
            value = ahdl.args[i + 1]
            port  = ahdl.args[i + 2]
            eqs.append(AHDL_OP(cond, port, value))
        cond = functools.reduce(lambda a, b: AHDL_OP('And', a, b), eqs)
        return self.visit(cond)

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
            self.hdlmodule.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
            self.emit(f'/* {self.visit(ahdl.dst)} <= {self.visit(ahdl.src)}; */')
        elif ahdl.dst.is_a(AHDL_SUBSCRIPT) and ahdl.dst.memvar.sig.is_netarray():
            self.hdlmodule.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
            self.emit(f'/* {self.visit(ahdl.dst)} <= {self.visit(ahdl.src)}; */')
        else:
            src = self.visit(ahdl.src)
            dst = self.visit(ahdl.dst)
            if env.hdl_debug_mode:
                self.emit(f'$display("%8d:REG  :{self.hdlmodule.name:<10}', newline=False)
                self.emit(f'{dst} <= 0x%2h (%1d)", $time, {src}, {src});')
            self.emit(f'{dst} <= {src};')

    def visit_AHDL_MEM(self, ahdl):
        name = ahdl.name.hdl_name()
        offset = self.visit(ahdl.offset)
        return f'{name}[{offset}]'

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
        return f'{cond} ? {lexp} : {rexp}'

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
                        self.hdlmodule.remove_internal_net(exp.sig)
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

    def visit_AHDL_SIGNAL_DECL(self, ahdl):
        nettype = 'reg' if ahdl.sig.is_reg() else 'wire'
        self.emit(f'{nettype} {self._generate_signal(ahdl.sig)};')

    def visit_AHDL_SIGNAL_ARRAY_DECL(self, ahdl):
        nettype = 'reg' if ahdl.sig.is_regarray() else 'wire'
        name = self._safe_name(ahdl.sig)
        size = self.visit(ahdl.size)
        if ahdl.sig.width == 1:
            self.emit(f'{nettype} {name}[0:{size}-1];')
        else:
            sign = 'signed' if ahdl.sig.is_int() else ''
            self.emit(f'{nettype} {sign:<6} [{ahdl.sig.width-1}:0] {name} [0:{size}-1];')

    def visit_AHDL_ASSIGN(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit(f'assign {dst} = {src};')

    def visit_AHDL_EVENT_TASK(self, ahdl):
        evs = []
        for v, e in ahdl.events:
            var = self.visit(v)
            if e == 'rising':
                ev = 'posedge '
            elif e == 'falling':
                ev = 'negedge '
            else:
                ev = ''
            evs.append(f'{ev}{var}')
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
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_AHDL_META_WAIT(self, ahdl):
        assert False

    def visit_AHDL_FUNCTION(self, ahdl):
        self.emit(f'function [{ahdl.output.sig.width-1}:0] {self.visit(ahdl.output)} (')
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
        self.emit(f'{ahdl.val}: begin')
        self.set_indent(2)
        self.visit(ahdl.block)
        self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_TRANSITION(self, ahdl):
        state_var = AHDL_SYMBOL(self.current_state_sig.name)
        state = AHDL_SYMBOL(ahdl.target.name)
        self.visit(AHDL_MOVE(state_var, state))

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
        if env.dev_debug_mode and ahdl in self.hdlmodule.ahdl2dfgnode:
            self._emit_source_text(ahdl)
        return ret

    def _get_source_text(self, ahdl):
        node = self.hdlmodule.ahdl2dfgnode[ahdl]
        if node.tag.loc.lineno < 1:
            return
        text = get_src_text(node.tag.loc.filename, node.tag.loc.lineno)
        text = text.strip()
        if not text:
            return
        if text[-1] == '\n':
            text = text[:-1]
        filename = os.path.basename(node.tag.loc.filename)
        return f'{filename} [{node.tag.loc.lineno}]: {text}'

    def _emit_source_text(self, ahdl):
        text = self._get_source_text(ahdl)
        if text:
            self.emit(f'/* {text} */', continueus=True)
