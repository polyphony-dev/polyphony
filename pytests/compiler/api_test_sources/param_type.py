from polyphony import module, testbench
from polyphony.io import Port
from polyphony.typing import int8


@module
class param_type:
    def __init__(self, dtype: type):
        self.p = Port(dtype, 'out', 10)


@testbench
def test():
    m = param_type(int8)
    assert m.p.rd() == 10
