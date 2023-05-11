from dataclasses import dataclass
from ..common.common import Tagged


class Signal(Tagged):
    TAGS = {
        'reg',  # reg is a reg in VerilogHDL
        'net',  # net is a wire in VerilogHDL
        'int', 'condition',
        'regarray', 'netarray', 'rom',
        'parameter', 'constant',
        'single_port',  # port is an I/O port, either input or output
        'input', 'output',
        'accessor',     # accessor is a local signal which accessing a submodule's port
        'field', 'ctrl', 'onehot',
        'initializable',
        'induction',
        'pipelined',
        'pipeline_ctrl',
        'rewritable',
        'interface', 'subscope', 'dut',
        'self'
    }

    def __init__(self, hdlscope, name, width, tags, sym=None):
        super().__init__(tags)
        self.hdlscope = hdlscope
        self.name = name
        self.width = width  # width:int | (width:int, array_length:int)
        self.sym = sym
        self.init_value = 0

    def __str__(self):
        return f'{self.name}<{self.width}> {self.tags}'

    def __eq__(self, other):
        return self.name == other.name

    def __lt__(self, other):
        return self.name < other.name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "Signal(\'{}\', {}, {})".format(self.name, self.width, self.tags)

    def prefix(self):
        return self.name[:-len(self.sym.hdl_name())]
