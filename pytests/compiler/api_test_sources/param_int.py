from polyphony import module, testbench
from polyphony.io import Port


@module
class param_int:
    def __init__(self, width):
        self.p = Port(int, 'out', width)


@testbench
def test():
    m = param_int(42)
    assert m.p.rd() == 42
