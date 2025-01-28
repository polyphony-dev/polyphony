from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep


@module
class Submodule:
    def __init__(self, param):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.param = param


@module
class Nesting01:
    def __init__(self):
        self.sub1 = Submodule(2)
        #self.sub2 = Submodule(3)
        self.append_worker(self.worker, loop=False)
        #self.append_worker(self.worker, self.sub2)

    def worker(self):
        while is_worker_running():
            v = self.sub1.i.rd() * self.sub1.param
            print('v', v)
            self.sub1.o.wr(v)


@testbench
def test(m):
    m.sub1.i.wr(10)
    # m.sub2.i.wr(20)
    clksleep(10)
    print(m.sub1.o.rd())
    assert m.sub1.o.rd() == 20
    # assert m.sub2.o.rd() == 60


m = Nesting01()
test(m)
