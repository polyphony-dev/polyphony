from .ahdl import *
from .env import env
from .vericodegen import VerilogCodeGen
from .hdlmodule import RAMModule
from .hdlinterface import *
from logging import getLogger
logger = getLogger(__name__)


class VerilogTestGen(VerilogCodeGen):
    def __init__(self, hdlmodule):
        super().__init__(hdlmodule)
        clk = self.hdlmodule.gen_sig('clk', 1, {'reserved'})
        rst = self.hdlmodule.gen_sig('rst', 1, {'reserved'})
        self.hdlmodule.add_internal_reg(clk)
        self.hdlmodule.add_internal_reg(rst)

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
        self._generate_reset_task()
        self.emit('\n')
        #self._generate_test_main()
        for fsm in self.hdlmodule.fsms.values():
            self._generate_process(fsm)

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

    def _generate_monitor_task(self):
        if not (env.enable_verilog_monitor or env.enable_verilog_dump):
            return

        def add_ports(ports):
            for p in ports:
                if isinstance(p, tuple):
                    accessor_name = accessor.port_name(p)
                    args.append(accessor_name)
                    if p.width == 1:
                        formats.append(f'{accessor_name}=%1d')
                    else:
                        formats.append(f'{accessor_name}=%4d')

        self.emit('initial begin')
        self.set_indent(2)

        formats = []
        args = ['$time']
        for name, sub_module, _, _, in self.hdlmodule.sub_modules.values():
            if isinstance(sub_module, RAMModule):
                continue
            if not sub_module.interfaces:
                continue
            for inf in sub_module.interfaces.values():
                if isinstance(inf, SinglePortInterface):
                    accessor = inf.accessor(name)
                    add_ports(accessor.ports)
        format_text = '"%5t:' + ', '.join(formats) + '"'
        args_text = ', '.join(args)

        if env.enable_verilog_monitor:
            self.emit(f'$monitor({format_text}, {args_text});')
        if env.enable_verilog_dump:
            self.emit(f'$dumpfile("{self.hdlmodule.name}.vcd");')
            self.emit(f'$dumpvars(0, {self.hdlmodule.name});')
        self.set_indent(-2)
        self.emit('end')
