from polyphony import module, pure
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep


@module
class Submodule:
    @pure
    def __init__(self, param):
        self.i = Port(int8)
        self.o = Port(int8)
        self.param = param


@module
class Nesting01:
    @pure
    def __init__(self):
        self.sub1 = Submodule(2)
        self.sub2 = Submodule(3)
        self.append_worker(self.worker, self.sub1)
        self.append_worker(self.worker, self.sub2)

    def worker(self, sub):
        while is_worker_running():
            v = sub.i.rd() * sub.param
            sub.o.wr(v)


@testbench
def test(m):
    m.sub1.i.wr(10)
    m.sub2.i.wr(20)
    clksleep(10)
    assert m.sub1.o.rd() == 20
    assert m.sub2.o.rd() == 60


m = Nesting01()
test(m)
