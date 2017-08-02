from polyphony import module, pure
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep, wait_value


@module
class Submodule:
    @pure
    def __init__(self, param):
        self.i = Port(int8)
        self.o = Port(int8)
        self.param = param
        self.append_worker(self.sub_worker)

    def sub_worker(self):
        while is_worker_running():
            v = self.i.rd() * self.param
            self.o.wr(v)


@module
class Nesting03:
    @pure
    def __init__(self):
        self.sub1 = Submodule(2)
        self.sub2 = Submodule(3)
        self.append_worker(self.worker)
        self.start = Port(bool, 'in', init=False)
        self.result = Port(bool, 'out', init=False, protocol='valid')

    def worker(self):
        wait_value(True, self.start)
        self.sub1.i.wr(10)
        self.sub2.i.wr(20)
        clksleep(10)
        result1 = self.sub1.o.rd() == 20
        result2 = self.sub2.o.rd() == 60
        self.result.wr(result1 and result2)


@testbench
def test(m):
    m.start.wr(True)
    assert True == m.result.rd()


m = Nesting03()
test(m)
