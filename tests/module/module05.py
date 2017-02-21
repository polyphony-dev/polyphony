from polyphony import module
from polyphony import testbench
from polyphony.timing import wait_value
from polyphony.io import Int


class Interface:
    def __init__(self):
        self.i0 = Int(8)
        self.i1 = Int(8)
        self.o0 = Int(8)
        self.o1 = Int(8)


@module
class ModuleTest05:
    def __init__(self, param):
        self.inf = Interface()
        self.set_param(param)
        self.append_worker(self.worker, 'foo', self.inf.i0, self.inf.o0)
        self.append_worker(self.worker, 'bar', self.inf.i1, self.inf.o1)

    def worker(self, name, i, o):
        wait_value(self.param, i)
        print('worker', name, i.rd())
        o.wr(1)

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
