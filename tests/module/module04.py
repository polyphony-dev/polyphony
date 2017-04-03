from polyphony import module
from polyphony import testbench
from polyphony.timing import wait_value
from polyphony.io import Port
from polyphony.typing import bit

class Interface:
    def __init__(self):
        self.i0 = Port(bit)
        self.i1 = Port(bit)
        self.o0 = Port(bit)
        self.o1 = Port(bit)


@module
class ModuleTest04:
    def __init__(self):
        self.inf = Interface()
        self.append_worker(self.worker, 'foo', self.inf.i0, self.inf.o0)
        self.append_worker(self.worker, 'bar', self.inf.i1, self.inf.o1)

    def worker(self, name, i, o):
        wait_value(1, i)
        print('worker', name, i.rd())
        o.wr(1)


@testbench
def test(m):
    m.inf.i0.wr(1)
    wait_value(1, m.inf.o0)
    assert m.inf.o0.rd() == 1

    m.inf.i1.wr(1)
    wait_value(1, m.inf.o1)
    assert m.inf.o1.rd() == 1


m = ModuleTest04()
test(m)
