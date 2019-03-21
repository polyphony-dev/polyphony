from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import clkfence


@module
class assign01:
    def __init__(self, param):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out')
        self.o.assign(lambda:self.i.rd() + param + 1)


m = assign01(5)


@testbench
def test(m):
    m.i.wr(10)
    clkfence()
    assert 16 == m.o.rd()


test(m)
