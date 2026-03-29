from polyphony import module, testbench
from polyphony.io import Port


@module
class object_pass:
    def __init__(self, width):
        self.p = Port(int, 'out', width)


@testbench
def test():
    m = object_pass(99)
    assert m.p.rd() == 99
