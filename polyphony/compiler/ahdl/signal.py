from __future__ import annotations

from typing import TYPE_CHECKING

from ..common.common import Tagged

if TYPE_CHECKING:
    from typing import Callable


class Signal(Tagged):
    TAGS = {
        'reg',  # reg is a reg in VerilogHDL
        'net',  # net is a wire in VerilogHDL
        'int', 'condition',
        'regarray', 'netarray', 'rom',
        'parameter', 'constant',
        'single_port',  # port is an I/O port, either input or output
        'input', 'output',
        'connector',     # connector is a local signal which accessing a submodule's port
        'field', 'ctrl', 'onehot',
        'initializable',
        'induction',
        'pipelined',
        'pipeline_ctrl',
        'rewritable',
        'subscope', 'dut',
        'self'
    }

    # Type stubs for dynamic is_<tag>() methods from Tagged.__getattr__
    is_reg: Callable[[], bool]
    is_net: Callable[[], bool]
    is_int: Callable[[], bool]
    is_regarray: Callable[[], bool]
    is_netarray: Callable[[], bool]
    is_input: Callable[[], bool]
    is_output: Callable[[], bool]

    def __init__(self, hdlscope, name, width, tags, sym=None):
        super().__init__(tags)
        self.hdlscope = hdlscope
        self.name = name
        self.width = width  # width:int | (width:int, array_length:int)
        self.sym = sym
        self.init_value = 0

    def __str__(self):
        return f'{self.name}<{self.width}> {sorted(self.tags)}'

    def __eq__(self, other):
        return self.name == other.name

    def __lt__(self, other):
        return self.name < other.name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "Signal(\'{}\', {}, {})".format(self.name, self.width, self.tags)

    def prefix(self):
        assert self.sym is not None
        return self.name[:-len(self.sym.hdl_name())]
