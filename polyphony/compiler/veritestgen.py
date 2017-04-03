from .ahdl import *
from .vericodegen import VerilogCodeGen
from .hdlmoduleinfo import RAMModuleInfo
from .hdlinterface import *
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
        self.module_info.add_constant('CLK_PERIOD', clk_period)
        self.module_info.add_constant('CLK_HALF_PERIOD', int(clk_period / 2))
        self.module_info.add_constant('INITIAL_RESET_SPAN', clk_period * 10)

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
        for fsm in self.module_info.fsms.values():
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
        def add_ports(ports):
            for p in ports:
                if isinstance(p, tuple):
                    accessor_name = accessor.port_name(p)
                    args.append(accessor_name)
                    if p.width == 1:
                        formats.append('{}=%1d'.format(accessor_name))
                    else:
                        formats.append('{}=%4d'.format(accessor_name))

        self.emit('initial begin')
        self.set_indent(2)

        formats = []
        args = ['$time']

        for name, info, connections, _, in self.module_info.sub_modules.values():
            if isinstance(info, RAMModuleInfo):
                continue
            if not info.interfaces:
                continue
            for inf in info.interfaces.values():
                if isinstance(inf, SinglePortInterface):
                    accessor = inf.accessor(name)
                    ports = accessor.ports.all()
                    add_ports(ports)
        format_text = '"%5t:' + ', '.join(formats) + '"'
        args_text = ', '.join(args)

        self.emit('$monitor({}, {});'.format(format_text, args_text))

        self.set_indent(-2)
        self.emit('end')

