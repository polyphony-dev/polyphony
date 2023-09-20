from .vericodegen import VerilogCodeGen
from ...ahdl.ahdl import *
from ...common.env import env
from logging import getLogger
logger = getLogger(__name__)


class VerilogTestGen(VerilogCodeGen):
    def __init__(self, hdlmodule):
        super().__init__(hdlmodule)

    def generate(self):
        """output verilog module format:

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

        clk_period = 10
        self.hdlmodule.add_constant('CLK_PERIOD', clk_period)
        self.hdlmodule.add_constant('CLK_HALF_PERIOD', int(clk_period / 2))
        self.hdlmodule.add_constant('INITIAL_RESET_SPAN', clk_period * 10)

        self._generate_include()
        self._generate_module()
        self.set_indent(2)
        self._generate_clock_task()
        self._generate_reset_task()
        if env.enable_verilog_dump:
            self._generate_dump_vcd_task()
        self.set_indent(-2)
        self.emit('endmodule\n')

    def _generate_clock_task(self):
        self.emit('initial begin')
        self.set_indent(2)
        self.emit('clk = 0;')
        self.emit('#CLK_HALF_PERIOD')
        self.emit('forever #CLK_HALF_PERIOD clk = ~clk;')
        self.set_indent(-2)
        self.emit('end')

    def _generate_reset_task(self):
        self.emit('initial begin')
        self.set_indent(2)
        self.emit('rst <= 1;')
        self.emit('#INITIAL_RESET_SPAN')
        self.emit('rst <= 0;')
        self.set_indent(-2)
        self.emit('end')

    def _generate_dump_vcd_task(self):
        self.emit('initial begin')
        self.set_indent(2)
        self.emit(f'$dumpfile("{self.hdlmodule.name}.vcd");')
        for reg in self.hdlmodule.get_signals({'reg'}, {'input', 'output'}):
            self.emit(f'$dumpvars(0, {self._safe_name(reg.name)});')
        for reg in self.hdlmodule.get_signals({'regarray'}, {'input', 'output'}):
            for i in range(reg.width[1]):
                self.emit(f'$dumpvars(0, {self._safe_name(reg.name)}[{i}]);')
        for net in self.hdlmodule.get_signals({'net'}, {'input', 'output'}):
            self.emit(f'$dumpvars(0, {self._safe_name(net.name)});')
        for net in self.hdlmodule.get_signals({'netarray'}, {'input', 'output'}):
            for i in range(net.width[1]):
                self.emit(f'$dumpvars(0, {self._safe_name(net.name)}[{i}]);')
        self.set_indent(-2)
        self.emit('end')
