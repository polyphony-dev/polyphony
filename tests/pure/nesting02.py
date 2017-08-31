from polyphony import module, pure
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep


@module
class Submodule1:
    #@pure
    def __init__(self, param):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.param = param
        self.append_worker(self.sub_worker)

    def sub_worker(self):
        while is_worker_running():
            v = self.i.rd() * self.param
            self.o.wr(v)


@module
class Submodule2:
    @pure
    def __init__(self, param):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.param = param
        self.append_worker(self.sub_worker, self.i, self.o, self.param)

    def sub_worker(self, i, o, param):
        while is_worker_running():
            v = i.rd() * param
            o.wr(v)


@module
class Nesting02:
    @pure
    def __init__(self):
        self.sub1 = Submodule1(2)
        self.sub2 = Submodule2(3)


@testbench
def test(m):
    m.sub1.i.wr(10)
    m.sub2.i.wr(20)
    clksleep(10)
    assert m.sub1.o.rd() == 20
    assert m.sub2.o.rd() == 60


m = Nesting02()
test(m)
