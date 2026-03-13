from polyphony import module
from polyphony import testbench
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@timed
@module
class timed_reg_test:
    def __init__(self):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out', 0)
        self.append_worker(self.w)

    def w(self):
        clkfence()
        x = self.i.rd()
        clkfence()
        y = x + 10
        self.o.wr(y)
        clkfence()
        self.o.wr(x + 20)
        clkfence()


@timed
@testbench
def test():
    m = timed_reg_test()
    m.i.wr(5)
    clkfence()
    m.i.wr(99)
    clkfence()
    clkfence()
    x = m.o.rd()
    assert x == 15
    clkfence()
    x = m.o.rd()
    assert x == 25
    clkfence()
