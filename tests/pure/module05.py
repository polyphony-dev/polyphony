from polyphony import module, pure
from polyphony import testbench
from polyphony.timing import wait_value
from polyphony.io import Port
from polyphony.typing import int8


class Interface:
    def __init__(self):
        self.i0 = Port(int8)
        self.i1 = Port(int8)
        self.o0 = Port(int8)
        self.o1 = Port(int8)


@module
class ModuleTest05:
    @pure
    def __init__(self, param):
        self.inf = Interface()
        self.set_param(param)
        self.append_worker(self.worker0, 'foo', self.inf)
        self.append_worker(self.worker1, 'bar', self.inf)

    def worker0(self, name, inf):
        wait_value(self.param, inf.i0)
        print('worker', name, inf.i0.rd())
        inf.o0.wr(1)

    def worker1(self, name, inf):
        wait_value(self.param, inf.i1)
        print('worker', name, inf.i1.rd())
        inf.o1.wr(1)

    def set_param(self, p):
        # this line will be inlining
        self.param = p


PARAM = 100


@testbench
def test(m):
    m.inf.i0.wr(PARAM)
    wait_value(1, m.inf.o0)
    assert m.inf.o0.rd() == 1

    m.inf.i1.wr(PARAM)
    wait_value(1, m.inf.o1)
    assert m.inf.o1.rd() == 1


m = ModuleTest05(PARAM)
test(m)
