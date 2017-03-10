from polyphony import module
from polyphony import testbench
from polyphony.timing import wait_value
from polyphony.io import Uint


class Inf_A:
    def __init__(self, width):
        self.i = Uint(width)
        self.o = Uint(width)


class Inf_B:
    def __init__(self, width):
        self.i = Uint(width)
        self.o = Uint(width)


class Interfaces:
    def __init__(self, width):
        self.a = Inf_A(width)
        self.b = Inf_B(width)


@module
class ModuleTest06:
    def __init__(self, width):
        self.inf = Interfaces(width)
        self.append_worker(self.worker, 'foo', self.inf.a.i, self.inf.a.o)
        self.append_worker(self.worker, 'bar', self.inf.b.i, self.inf.b.o)

    def worker(self, name, i, o):
        wait_value(100, i)
        print('worker', name, i.rd())
        o.wr(200)


@testbench
def test(m):
    m.inf.a.i.wr(100)
    wait_value(200, m.inf.a.o)
    assert m.inf.a.o.rd() == 200

    m.inf.b.i.wr(100)
    wait_value(200, m.inf.b.o)
    assert m.inf.b.o.rd() == 200


m = ModuleTest06(8)
test(m)
