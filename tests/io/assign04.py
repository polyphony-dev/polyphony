from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@module
class assign04:
    def __init__(self):
        self.i0 = Port(int, 'in')
        self.i1 = Port(int, 'in')
        self.o = Port(int, 'out')
        self.o.assign(self.func)

    def func(self):
        if self.i0.rd():
            tmp = self.i0.rd()
        else:
            tmp = self.i1.rd()
        return tmp


@testbench
def test():
    m = assign04()
    m.i0.wr(0)
    m.i1.wr(10)
    clkfence()

    assert 10 == m.o.rd()

    m.i0.wr(1)
    m.i1.wr(11)
    clkfence()

    assert 1 == m.o.rd()

    clkfence()
