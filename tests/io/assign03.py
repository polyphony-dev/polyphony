from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@module
class assign03:
    def __init__(self, param):
        self.i = Port(int, 'in')
        self.o0 = Port(int, 'out')
        self.o1 = Port(int, 'out')
        self.param = param
        self.o0.assign(self.func0)
        self.o1.assign(self.func1)

    def func0(self):
        if self.i.rd() == 1:
            tmp = self.param * 2
        else:
            tmp = self.param
        return tmp

    def func1(self):
        tmp = self.param
        if self.i.rd() == 1:
            tmp = self.param * 2
        return tmp


m = assign03(5)


@testbench
def test(m):
    m.i.wr(1)
    clkfence()
    assert 10 == m.o0.rd()
    assert 10 == m.o1.rd()

    m.i.wr(0)
    clkfence()
    assert 5 == m.o0.rd()
    assert 5 == m.o1.rd()
    clkfence()


test(m)
