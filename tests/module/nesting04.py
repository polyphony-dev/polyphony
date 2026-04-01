from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep, wait_value
from polyphony.modules import Handshake


@module
class Submodule:
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
class Nesting04:
    def __init__(self):
        self.sub1 = Submodule(2)
        self.sub2 = Submodule(3)
        self.append_worker(self.worker)
        self.start = Port(bool, 'in', init=False)
        self.result = Handshake(bool, 'out')

    def worker(self):
        # Chain: input -> sub1 (*2) -> sub2 (*3) -> check
        wait_value(True, self.start)
        self.sub1.i.wr(5)
        clksleep(5)
        mid = self.sub1.o.rd()   # expect 10
        self.sub2.i.wr(mid)
        clksleep(5)
        final = self.sub2.o.rd()  # expect 30
        self.result.wr(final == 30)


@testbench
def test():
    m = Nesting04()
    m.start.wr(True)
    assert True == m.result.rd()
