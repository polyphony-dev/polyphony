from collections import defaultdict, OrderedDict
from .ir import Ctx
from .ahdl import *
from .env import env
from .vericodegen import VerilogCodeGen
from .common import INT_WIDTH
from .type import Type
from .hdlmoduleinfo import RAMModuleInfo
from logging import getLogger
logger = getLogger(__name__)

class VerilogTestGen(VerilogCodeGen):
    def __init__(self, scope):
        self.codes = []
        self.indent = 0
        self.scope = scope
        self.module_info = self.scope.module_info
        clk = self.scope.gen_sig('clk', 1)
        rst = self.scope.gen_sig('rst', 1)
        self.module_info.add_internal_reg(clk)
        self.module_info.add_internal_reg(rst)

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
        clk_period = 10 #TODO
        self.module_info.add_constant('CLK_PERIOD', clk_period)
        self.module_info.add_constant('CLK_HALF_PERIOD', int(clk_period/2))
        self.module_info.add_constant('INITIAL_RESET_SPAN', clk_period*10)

        self.set_indent(2)
        self._generate_main()
        self.set_indent(-2)
        main_code = self.result()
        self.codes = []

        self._generate_include()
        self._generate_module()
        self.set_indent(2)
        self._generate_monitor_task()
        self.set_indent(-2)
        self.emit(main_code)
        self.emit('endmodule\n')

    def _generate_main(self):
        self._generate_clock_task()
        self.emit('\n')
        self._generate_test_main()

    def _generate_clock_task(self):
        self.emit('initial begin')
        self.set_indent(2)
        self.emit('clk = 0;')
        self.emit('#CLK_HALF_PERIOD')
        self.emit('forever #CLK_HALF_PERIOD clk = ~clk;')
        self.set_indent(-2)
        self.emit('end')

    def _generate_test_main(self):
        self.emit('initial begin')
        self.set_indent(2)
        self.emit('rst <= 1;')
        self.emit('')
        self.emit('#INITIAL_RESET_SPAN')
        self.emit('rst <= 0;')
        self.emit('')

        for stg in self.scope.stgs:
            for i, state in enumerate(stg.states):
                self.emit('#CLK_PERIOD')
                self._process_State(state)
        self.emit('')
        self.emit('$finish;')
        self.set_indent(-2)
        self.emit('end')

    def _process_State(self, state):
        self.current_state = state
        code = '/* {} */'.format(state.name)
        self.emit(code)

        if env.hdl_debug_mode:
            self.emit('$display("state: {}::{}");'.format(self.scope.name, state.name))

        for code in state.codes:
            self.visit(code)

        self.emit('')

    def _generate_monitor_task(self):
        self.emit('initial begin')
        self.set_indent(2)

        formats = []
        args = ['$time']

        for name, info, _, _, _ in self.module_info.sub_modules.values():
            if isinstance(info, RAMModuleInfo):
                continue
            for p in info.interfaces[0].ports[3:]: # skip controls
                if isinstance(p, tuple):
                    accessor_name = info.interfaces[0].port_name(name, p)
                    args.append(accessor_name)
                    if p.width == 1:
                        formats.append('{}=%1d'.format(accessor_name))
                    else:
                        formats.append('{}=%4d'.format(accessor_name))
                            
        format_text = '"%5t:' + ', '.join(formats) + '"'
        args_text = ', '.join(args)

        self.emit('$monitor({}, {});'.format(format_text, args_text))

        self.set_indent(-2)
        self.emit('end')

    def visit_WAIT_INPUT_READY(self, ahdl):
        if ahdl.codes:
            for code in ahdl.codes:
                self.visit(code)

    def visit_WAIT_OUTPUT_ACCEPT(self, ahdl):
        pass

    def visit_ACCEPT_IF_VALID(self, ahdl):
        modulecall = ahdl.args[0]

        for i, arg in enumerate(modulecall.args):
            if arg.is_a(AHDL_MEMVAR):
                p, _, _ = modulecall.scope.params[i]
                assert Type.is_seq(p.typ)
                param_memnode = Type.extra(p.typ)
                if param_memnode.is_joinable() and param_memnode.is_writable():
                    csstr = '{}_{}_{}_cs'.format(modulecall.instance_name, i, arg.memnode.sym.hdl_name())
                    cs = self.scope.gen_sig(csstr, 1, ['memif'])
                    self.visit(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE), AHDL_CONST(0)))

        accept = self.scope.gen_sig(modulecall.prefix+'_accept', 1, ['reg'])
        self.visit(AHDL_MOVE(AHDL_VAR(accept, Ctx.STORE), AHDL_CONST(1)))

    def visit_GET_RET_IF_VALID(self, ahdl):
        modulecall = ahdl.args[0]
        dst = ahdl.args[1]
        sub_out = self.scope.gen_sig(modulecall.prefix+'_out_0', INT_WIDTH, ['wire', 'int'])
        self.visit(AHDL_MOVE(dst, AHDL_VAR(sub_out, Ctx.LOAD)))

    def visit_WAIT_RET_AND_GATE(self, ahdl):
        for modulecall in ahdl.args[0]:
            valid = self.scope.gen_sig(modulecall.prefix+'_valid', 1, ['wire'])
            cond = AHDL_OP('Eq', AHDL_VAR(valid, Ctx.LOAD), AHDL_CONST(1))

            if len(modulecall.scope.module_info.state_constants) > 1:
                condsym = self.scope.add_temp('@condtest')
                condsig = self.scope.gen_sig(condsym.hdl_name(), 1)
                self.module_info.add_static_assignment(AHDL_ASSIGN(AHDL_VAR(condsig, Ctx.STORE), cond))
                self.module_info.add_internal_net(condsig)
                self.emit('@(posedge {});'.format(condsig.name))

    def visit_AHDL_TRANSITION(self, ahdl):
        pass

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        pass
