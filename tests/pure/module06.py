from polyphony import module, pure
from polyphony import testbench
from polyphony.timing import wait_value
from polyphony.io import Port
from polyphony.typing import uint8


class Inf_A:
    def __init__(self, t):
        self.i = Port(t)
        self.o = Port(t)


class Inf_B:
    def __init__(self, t):
        self.i = Port(t)
        self.o = Port(t)


class Interfaces:
    def __init__(self, t):
        self.a = Inf_A(t)
        self.b = Inf_B(t)


@module
class ModuleTest06:
    @pure
    def __init__(self, t):
        self.inf = Interfaces(t)
        self.append_worker(self.worker_a, 'foo', self.inf.a.i, self.inf.a.o)
        self.append_worker(self.worker_b, 'bar', self.inf.b.i, self.inf.b.o)

    def worker_a(self, name, i, o):
        wait_value(100, i)
        print('worker', name, i.rd())
        o.wr(200)

    def worker_b(self, name, i, o):
        wait_value(101, i)
        print('worker', name, i.rd())
        o.wr(201)


@testbench
def test(m):
    m.inf.a.i.wr(100)
    wait_value(200, m.inf.a.o)
    assert m.inf.a.o.rd() == 200

    m.inf.b.i.wr(101)
    wait_value(201, m.inf.b.o)
    assert m.inf.b.o.rd() == 201


m = ModuleTest06(uint8)
test(m)
