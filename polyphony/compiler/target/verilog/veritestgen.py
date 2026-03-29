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
        if env.watch_signals:
            self._generate_monitor_task(env.watch_signals)
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

    def _generate_monitor_task(self, watch_signals):
        signal_names = [s.strip() for s in watch_signals.split(',')]
        # Resolve Python hierarchical names to Verilog testbench signal names
        # Python name "m.i" -> look for signal with name "m_i" in testbench scope
        verilog_names = []
        valid_names = []
        all_sigs = {sig.name: sig for sig in self.hdlmodule.get_signals(
            {'reg', 'net'}, {'input', 'output'})}
        # Also include input/output signals (scalar only)
        for sig in self.hdlmodule.get_signals({'input', 'output'}):
            all_sigs[sig.name] = sig
        for py_name in signal_names:
            v_name = py_name.replace('.', '_')
            if v_name in all_sigs:
                verilog_names.append(self._safe_name(v_name))
                valid_names.append(py_name)
            else:
                logger.warning(f"watch signal '{py_name}' not found as '{v_name}' in testbench")
        if not valid_names:
            return
        fmt_parts = ["%5t:"]
        args = ["$time"]
        for py_name, v_name in zip(valid_names, verilog_names):
            fmt_parts.append(f" {py_name}=%d")
            args.append(v_name)
        fmt_str = ''.join(fmt_parts)
        self.emit('initial begin')
        self.set_indent(2)
        self.emit(f'$monitor("{fmt_str}", {", ".join(args)});')
        self.set_indent(-2)
        self.emit('end')
