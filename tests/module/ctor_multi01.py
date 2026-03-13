from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value

FACTOR = 3


@module
class CtorMulti:
    def __init__(self, base, scale, offsets):
        self.o = Port(int, 'out')
        self.append_worker(self.work, base, scale, offsets)

    def work(self, base, scale, offsets):
        a, b = offsets
        self.o.wr(base * scale + a + b)


@testbench
def test0():
    # literal + global + tuple
    m = CtorMulti(10, FACTOR, (1, 2))
    wait_value(33, m.o)
    assert m.o.rd() == 33


@testbench
def test1():
    # different instances with different values
    m = CtorMulti(5, 2, (10, 20))
    wait_value(40, m.o)
    assert m.o.rd() == 40
