import math
from collections import OrderedDict
from .verilog_common import pyop2verilogop
from .ir import Ctx
from .signal import Signal
from .ahdl import AHDL_CONST, AHDL_VAR, AHDL_SYMBOL, AHDL_MOVE, AHDL_IF, AHDL_ASSIGN
from .env import env
from logging import getLogger
logger = getLogger(__name__)

class VerilogCodeGen:
    def __init__(self, scope):
        self.codes = []
        self.indent = 0
        self.scope = scope
        self.module_info = self.scope.module_info
        name = self.module_info.name
        clk_in = self.scope.gen_sig('CLK', 1, ['wire'])
        rst_in = self.scope.gen_sig('RST', 1, ['wire'])
        self.module_info.add_ctrl_input(clk_in)
        self.module_info.add_ctrl_input(rst_in)

    def result(self):
        return ''.join(self.codes)

    def emit(self, code):
        self.codes.append((' '*self.indent) + code)

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
        {internal_wires}
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
        self.emit('endmodule\n\n')

    def _generate_process(self, fsm):
        self.emit('always @(posedge CLK) begin\n')
        self.set_indent(2)
        self.emit('if (RST) begin\n')
        self.set_indent(2)

        for stg in fsm.stgs:
            if stg.is_main():
                main_stg = stg
        assert main_stg

        #outputs = list(self.module_info.data_outputs.values())
        #outputs.extend(self.module_info.ctrl_outputs.values())
        #outputs.extend(self.module_info.mem_outputs.values())
        for sig in fsm.outputs:
            if sig.is_reg():
                self.emit('{} <= 0;\n'.format(sig.name))
        #for sig in self.module_info.internal_regs:
        #    if not sig.is_statevar():
        #        self.emit('{} <= 0;\n'.format(sig.name))

        main_state_var = fsm.state_var #self.module_info.fsms[self.scope.name].state_var
        self.emit('{} <= {};\n'.format(main_state_var.name, main_stg.init_state.name))
        self.set_indent(-2)
        self.emit('end else begin //if (RST)\n')
        self.set_indent(2)

        self.emit('case({})\n'.format(main_state_var.name))

        for stg in fsm.stgs:
            for i, state in enumerate(stg.states()):
                self._process_State(state, main_state_var)

        self.emit('endcase\n')
        self.set_indent(-2)
        self.emit('end\n')#end if (READY)
        self.set_indent(-2)
        self.emit('end\n')
        self.emit('\n')

    def _generate_include(self):
        pass
        # self.emit('`include "SinglePortRam.v"\n')

    def _generate_module(self):
        self._generate_module_header()
        self.set_indent(2)
        self._generate_localparams()
        self._generate_internal_regs()
        self._generate_internal_wires()
        self._generate_functions()
        self._generate_muxes()
        self._generate_demuxes()        
        self._generate_sub_module_instances()
        self._generate_static_assignment()
        self._generate_sync_assignment()
        self._generate_field_access()
        self.set_indent(-2)

    def _generate_module_header(self):
        self.emit('module {}'.format(self.module_info.qualified_name))
        self.emit('\n')

        self.set_indent(2)
        self.emit('(\n')
        self.set_indent(2)
        inputs = list(self.module_info.data_inputs.values())
        inputs.extend(self.module_info.ctrl_inputs.values())
        inputs.extend(self.module_info.mem_inputs.values())
        for sig in inputs:
            typ = 'reg' if sig.is_reg() else 'wire'
            if sig.width == 1:
                self.emit('input {} {},\n'.format(typ, sig.name))
            else:
                self.emit('input {} signed [{}:0] {},\n'.format(typ, sig.width-1, sig.name))

        outputs = list(self.module_info.data_outputs.values())
        outputs.extend(self.module_info.ctrl_outputs.values())
        outputs.extend(self.module_info.mem_outputs.values())
        for i, sig in enumerate(outputs):
            typ = 'reg' if sig.is_reg() else 'wire'
            if i < len(outputs)-1:
                delim = ',\n'
            else:
                delim = ''
            if sig.width == 1:
                self.emit('output {} {}{}'.format(typ, sig.name, delim))
            else:
                self.emit('output {} signed [{}:0] {}{}'.format(typ, sig.width-1, sig.name, delim))

        self.set_indent(-2)
        self.emit(');\n')
        self.set_indent(-2)
        self.emit('\n')

    def _generate_signal(self, sig):
        sign = 'signed' if sig.is_int() else ''
        return '{:<6} [{}:0] {}'.format(sign, sig.width-1, sig.name)

    def _generate_localparams(self):
        self.emit('//localparams\n')
        for name, val in self.module_info.constants:
            self.emit('localparam {0} = {1};\n'.format(name, val))
        self.emit('\n')

    def _generate_internal_regs(self):
        if self.module_info.internal_regs:
            self.emit('//internal regs\n')
        for sig in sorted(self.module_info.internal_regs, key=lambda sig: sig.name):
            if sig.width == 1:
                self.emit('reg {};\n'.format(sig.name))
            else:
                self.emit('reg {};\n'.format(self._generate_signal(sig)))
        self.emit('\n')

        for sig, size in sorted(self.module_info.internal_reg_arrays, key=lambda v: v[0].name):
            if sig.width == 1:
                self.emit('reg {}[0:{}];\n'.format(sig.name, size-1))
            else:
                sign = 'signed' if sig.is_int() else ''
                self.emit('reg {:<6} [{}:0] {} [0:{}];\n'.format(sign, sig.width-1, sig.name, size-1))
        self.emit('\n')


    def _generate_internal_wires(self):
        if self.module_info.internal_wires:
            self.emit('//internal wires\n')
        for sig in sorted(self.module_info.internal_wires, key=lambda sig: sig.name):
            if sig.width == 1:
                self.emit('wire {};\n'.format(sig.name))
            else:
                self.emit('wire {};\n'.format(self._generate_signal(sig)))
        self.emit('\n')

    def _generate_functions(self):
        if self.module_info.functions:
            self.emit('//functions\n')
        for func in self.module_info.functions:
            self.visit(func)

    def _generate_muxes(self):
        if self.module_info.muxes:
            self.emit('//muxes\n')
        for mux in self.module_info.muxes:
            self.visit(mux)

    def _generate_demuxes(self):
        if self.module_info.demuxes:
            self.emit('//demuxes\n')
        for demux in self.module_info.demuxes:
            self.visit(demux)

    def _generate_sub_module_instances(self):
        self.emit('//sub module instances\n')
        for name, info, port_map, param_map in self.module_info.sub_modules.values():
            ports = []
            ports.append('.CLK(CLK)')
            ports.append('.RST(RST)')
            for port, signal in port_map.items():
                ports.append('.{}({})'.format(port, signal))
            if param_map:
                params = []
                for param_name, value in param_map.items():
                    params.append('.{}({})'.format(param_name, value))

                code = '{}#({}) {}({});\n'.format(info.qualified_name, ', '.join(params), name, ', '.join(ports))
            else:
                code = '{} {}({});\n'.format(info.qualified_name, name, ', '.join(ports))
            self.emit(code)
        self.emit('\n')

    def _generate_static_assignment(self):
        self.emit('//assigns\n')
        for assign in self.module_info.static_assignments:
            self.visit(assign)

        self.emit('\n')

    def _generate_sync_assignment(self):
        self.emit('//assigns\n')
        for assign in self.module_info.sync_assignments:
            self.emit('always @(posedge CLK) begin\n')
            self.set_indent(2)
            self.visit(assign)
            self.set_indent(-2)
            self.emit('end\n')
            self.emit('\n')

    def _generate_field_access(self):
        for field, access in self.module_info.field_accesses.items():
            self.emit('always @(posedge CLK) begin: {}_access\n'.format(field.name))
            self.set_indent(2)
            self.visit(access)
            self.set_indent(-2)
            self.emit('end\n')
            self.emit('\n')

    def _process_State(self, state, state_sig):
        self.current_state = state
        code = '{0}: begin\n'.format(state.name)
        self.emit(code)
        self.set_indent(2)
        if env.hdl_debug_mode:
            self.emit('$display("state: {}::{}::{}");\n'.format(self.scope.name, state_sig, state.name))

        for code in state.codes:
            self.visit(code)

        #add state transition code
        stg = state.stg
        state_var = AHDL_VAR(state_sig, Ctx.STORE)
        assert state.next_states
        cond1, nstate1, _ = state.next_states[0]
        if cond1 is None or cond1.is_a(AHDL_CONST):
            self.visit(AHDL_MOVE(state_var, AHDL_SYMBOL(nstate1.name)))
        else:
            cond_list = []
            codes_list = []
            for cond, nstate, codes in state.next_states:
                mv = AHDL_MOVE(state_var, AHDL_SYMBOL(nstate.name))
                cond_list.append(cond)
                if codes:
                    codes_list.append(codes + [mv])
                else:
                    codes_list.append([mv])
            self.visit(AHDL_IF(cond_list, codes_list))

        self.set_indent(-2)
        self.emit('end\n')

    def visit_AHDL_CONST(self, ahdl):
        if ahdl.value is None:
            return "'bx";
        elif isinstance(ahdl.value, bool):
            return str(int(ahdl.value))
        return str(ahdl.value)

    def visit_AHDL_VAR(self, ahdl):
        return ahdl.sig.name

    def visit_AHDL_MEMVAR(self, ahdl):
        assert 0

    def visit_AHDL_SYMBOL(self, ahdl):
        return ahdl.name

    def visit_AHDL_CONCAT(self, ahdl):
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
        return self.emit('/*' + str(ahdl.info) + '*/\n')

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR) and ahdl.dst.sig.is_condition():
            self.module_info.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
        else:
            src = self.visit(ahdl.src)
            dst = self.visit(ahdl.dst)
            if env.hdl_debug_mode:
                self.emit('$display("{}::{} <= 0x%2h (%1d)", {}, {});\n'.format(self.scope.name, dst, src, src))
            self.emit('{} <= {};\n'.format(dst, src))

    def visit_AHDL_STORE(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.mem)
        self.emit('{} <= {};\n'.format(dst, src))

    def visit_AHDL_LOAD(self, ahdl):
        src = self.visit(ahdl.mem)
        dst = self.visit(ahdl.dst)
        self.emit('{} <= {};\n'.format(dst, src))

    def visit_AHDL_MEM(self, ahdl):
        name = ahdl.name.hdl_name()
        offset = self.visit(ahdl.offset)
        return '{}[{}]'.format(name, offset)

    def visit_AHDL_IF(self, ahdl):
        cond0 = self.visit(ahdl.conds[0])
        if cond0[0] != '(':
            cond0 = '('+cond0+')'
        self.emit('if {} begin\n'.format(cond0))
        self.set_indent(2)
        for code in ahdl.codes_list[0]:
            self.visit(code)
        self.set_indent(-2)
        for cond, codes in zip(ahdl.conds[1:], ahdl.codes_list[1:]):
            if cond:
                cond = self.visit(cond)
                if cond[0] != '(':
                    cond = '('+cond+')'
                self.emit('end else if {} begin\n'.format(cond))
                self.set_indent(2)
                for code in codes:
                    self.visit(code)
                self.set_indent(-2)
            else:
                self.emit('end else begin\n')
                self.set_indent(2)
                for code in ahdl.codes_list[-1]:
                    self.visit(code)
                self.set_indent(-2)
        self.emit('end\n')

    def visit_AHDL_IF_EXP(self, ahdl):
        cond = self.visit(ahdl.cond)
        lexp = self.visit(ahdl.lexp)
        rexp = self.visit(ahdl.rexp)
        return '{} ? {} : {}'.format(cond, lexp, rexp)

    def visit_AHDL_FUNCALL(self, ahdl):
        return '{}({})'.format(ahdl.name, ', '.join([self.visit(arg) for arg in ahdl.args]))

    def visit_AHDL_PROCCALL(self, ahdl):
        args = []
        for arg in ahdl.args:
            a = self.visit(arg)
            args.append(a)

        if ahdl.name == '!hdl_print':
            self.emit('$display("%1d", {});\n'.format(', '.join(args)))
        elif ahdl.name == '!hdl_assert':
            #expand condtion expression for the assert message
            exp = args[0]
            if exp.startswith('cond'):
                remove_assign = []
                for assign in self.module_info.static_assignments:
                    if assign.dst.sig.name == exp:
                        remove_assign.append(assign)
                        expsig = self.scope.gen_sig(exp, 1)
                        self.module_info.internal_wires.remove(expsig)
                        exp = self.visit(assign.src)
                for assign in remove_assign:
                    self.module_info.static_assignments.remove(assign)
            exp = exp.replace('==', '===').replace('!=', '!==')
            code = 'if (!{}) begin\n'.format(exp)
            self.emit(code)
            code = '  $display("ASSERTION FAILED {}"); $finish;\n'.format(exp)
            self.emit(code)
            self.emit('end\n')
        else:
            self.emit('{}({});\n'.format(ahdl.name, ', '.join(args)))

    def visit_AHDL_ASSIGN(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('assign {} = {};\n'.format(dst, src))

    def visit_AHDL_CONNECT(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('{} = {};\n'.format(dst, src))

    def visit_AHDL_META(self, ahdl):
        pass
        #if ahdl.metaid == 'STG_JUMP':
        #    stg_name = ahdl.args[0]
        #    stg = self.scope.find_stg(stg_name)
        #    target_state = stg.init_state
        #    _, ret_state, _ = self.current_state.next_states[0]
        #    logger.debug(stg_name)
        #    self.stg_return_state[stg_name] = ret_state
        #
        #    self.current_state.next_states = []
        #    self.current_state.set_next((AHDL_CONST(1), target_state, None))
    
    def visit_AHDL_FUNCTION(self, ahdl):
        self.emit('function [{}:0] {} (\n'.format(ahdl.output.sig.width-1, ahdl.output.sig.name))
        self.set_indent(2)
        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}\n'.format(input.sig.width-1, input.sig.name))
            else:
                self.emit('input [{}:0] {},\n'.format(input.sig.width-1, input.sig.name))
        #self.emit(',\n'.join([str(i) for i in ahdl.inputs]))
        self.set_indent(-2)
        self.emit(');\n')
        self.emit('begin\n')
        self.set_indent(2)
        for stm in ahdl.stms:
            self.visit(stm)
        self.set_indent(-2)
        self.emit('end\n')        
        self.emit('endfunction\n')

    def visit_AHDL_CASE(self, ahdl):
        self.emit('case ({})\n'.format(self.visit(ahdl.sel)))
        self.set_indent(2)
        for item in ahdl.items:
            self.visit(item)
        self.set_indent(-2)
        self.emit('endcase\n')

    def visit_AHDL_CASE_ITEM(self, ahdl):
        self.emit("{}:".format(ahdl.val))
        self.visit(ahdl.stm)

    def visit_AHDL_MUX(self, ahdl):
        self.emit('function [{}:0] {} (\n'.format(ahdl.output.width-1, ahdl.name))
        self.set_indent(2)
        
        self.emit('input [{}:0] {},\n'.format(ahdl.selector.sig.width-1, ahdl.selector.sig.name))
        
        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}\n'.format(input.width-1, input.name))
            else:
                self.emit('input [{}:0] {},\n'.format(input.width-1, input.name))
            
        self.set_indent(-2)
        self.emit(');\n')
        self.emit('begin\n')
        self.set_indent(2)

        self.emit('case (1\'b1)\n')
        self.set_indent(2)
        for i, input in enumerate(ahdl.inputs):
            self.emit("{}[{}]: {} = {};\n".format(ahdl.selector.sig.name, i, ahdl.name, input.name))
        self.set_indent(-2)
        self.emit('endcase\n')
        self.set_indent(-2)
        self.emit('end\n')        
        self.emit('endfunction\n')

        params = self.visit(ahdl.selector) + ', '
        params += ', '.join([input.name for input in ahdl.inputs])
        self.emit('assign {} = {}({});\n'.format(ahdl.output.name, ahdl.name, params))

    def visit_AHDL_DEMUX(self, ahdl):
        if len(ahdl.outputs) > 1:
            for i, output in enumerate(ahdl.outputs):
                if isinstance(ahdl.input, Signal):
                    self.emit('assign {} = 1\'b1 == {}[{}] ? {}:{}\'bz;\n'.format(output.name, ahdl.selector.sig.name, i, ahdl.input.name, ahdl.input.width))
                elif isinstance(ahdl.input, int):
                    self.emit('assign {} = 1\'b1 == {}[{}] ? {}:{}\'bz;\n'.format(output.name, ahdl.selector.sig.name, i, ahdl.input, ahdl.width))
        else:
            self.emit('assign {} = {};\n'.format(ahdl.outputs[0].name, ahdl.input.name))

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

        self.emit('endmodule\n')

    def _generate_posi_reset(self):
        self.set_indent(2)
        self.emit('wire reset;\n')
        self.emit('assign reset = !S_AXI_ARESETN;\n')
        self.emit('\n')
        self.set_indent(-2)

    def _generate_top_module_instances(self):
        self.set_indent(2)
        self.emit('//main module instances\n')
        for module_info in self.mains:
            ports = []
            ports.append('.CLK(S_AXI_ACLK)')
            ports.append('.RST(reset)')
            #for port, (signal, _, _, _) in port_map.items():
            #    ports.append('.{}({})'.format(port, signal))
            code = '{} {}_inst({});\n'.format(module_info.name, module_info.name, ', '.join(ports))
            self.emit(code)
        self.set_indent(-2)
        self.emit('\n')


   
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

