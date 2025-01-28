from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import clkfence


@module
class assign01:
    def __init__(self, param):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out')
        self.o.assign(lambda:self.i.rd() + param + 1)


@testbench
def test():
    m = assign01(5)
    m.i.wr(10)
    clkfence()
    assert 16 == m.o.rd()
