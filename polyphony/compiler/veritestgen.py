from collections import defaultdict, OrderedDict
from .ir import Ctx
from .ahdl import AHDL_CONST, AHDL_VAR, AHDL_MOVE, AHDL_IF, AHDL_ASSIGN
from .env import env
from .vericodegen import VerilogCodeGen
from logging import getLogger
logger = getLogger(__name__)

class VerilogTestGen(VerilogCodeGen):
    def __init__(self, scope):
        self.codes = []
        self.indent = 0
        self.scope = scope
        self.module_info = self.scope.module_info
        clk = self.scope.gen_sig('CLK', 1)
        rst = self.scope.gen_sig('RST', 1)
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
        self.emit('endmodule\n\n')

    def _generate_main(self):
        self._generate_clock_task()
        self.emit('\n\n')
        self._generate_test_main()

    def _generate_clock_task(self):
        self.emit('initial begin\n')
        self.set_indent(2)
        self.emit('CLK = 0;\n')
        self.emit('#CLK_HALF_PERIOD\n')
        self.emit('forever #CLK_HALF_PERIOD CLK = ~CLK;\n')
        self.set_indent(-2)
        self.emit('end')

    def _generate_test_main(self):
        self.emit('initial begin\n')
        self.set_indent(2)
        self.emit('RST <= 1;\n')
        self.emit('\n')
        self.emit('#INITIAL_RESET_SPAN\n')
        self.emit('RST <= 0;\n')
        self.emit('\n')

        for stg in self.scope.stgs:
            for i, state in enumerate(stg.states()):
                self.emit('#CLK_PERIOD\n')
                self._process_State(state)
        self.emit('\n')
        self.emit('$finish;\n')
        self.set_indent(-2)
        self.emit('end\n')

    def _process_State(self, state):
        self.current_state = state
        code = '/* {} */\n'.format(state.name)
        self.emit(code)

        if env.hdl_debug_mode:
            self.emit('$display("state: {}::{}");\n'.format(self.scope.name, state.name))

        for code in state.codes:
            self.visit(code)

        #add state transition code
        assert state.next_states
        cond, nstate, codes = state.next_states[0]
        if cond is None or cond.is_a(AHDL_CONST):
            pass
        else:
            condsym = self.scope.add_temp('@condtest')
            condsig = self.scope.gen_sig(condsym.hdl_name(), 1)
            self.module_info.add_static_assignment(AHDL_ASSIGN(AHDL_VAR(condsig, Ctx.STORE), cond))
            self.emit('@(posedge {});\n'.format(condsig.name))
            for c in codes:
                self.visit(c)

        self.emit('\n')

    def _generate_monitor_task(self):
        self.emit('initial begin\n')
        self.set_indent(2)

        formats = []
        args = ['$time']

        for _, info, port_map, _ in self.module_info.sub_modules.values():
            for param, signal in port_map.items():
                ports = list(info.data_inputs.values())
                ports.extend(info.data_outputs.values())
                for iosig in ports:
                    if iosig.name == param: # TODO: filtering for data I/O port
                        args.append(signal.name)
                        if iosig.width == 1:
                            formats.append('{}=%b'.format(signal))
                        else:
                            formats.append('{}=%4d'.format(signal))
        format_text = '"%5t:' + ', '.join(formats) + '"'
        args_text = ', '.join(args)

        self.emit('$monitor({}, {});\n'.format(format_text, args_text))

        self.set_indent(-2)
        self.emit('end')
