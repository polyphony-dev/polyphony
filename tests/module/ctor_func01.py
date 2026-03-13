from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


def compute(x):
    return x * 2


@module
class CtorFunc:
    def __init__(self, fn):
        self.o = Port(int, 'out')
        self.append_worker(self.work, fn)

    def work(self, fn):
        self.o.wr(fn(21))


@testbench
def test0():
    m = CtorFunc(compute)
    wait_value(42, m.o)
    assert m.o.rd() == 42
