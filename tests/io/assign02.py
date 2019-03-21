from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import clkfence


@module
class assign02:
    def __init__(self, param):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out')
        self.param = param
        self.o.assign(self.func)

    def func(self):
        tmp = self.i.rd() + self.param
        tmp += 1
        return tmp


m = assign02(5)


@testbench
def test(m):
    m.i.wr(10)
    clkfence()
    assert 16 == m.o.rd()


test(m)
