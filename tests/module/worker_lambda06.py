"""Lambda calling a module method via self."""
from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda06:
    def __init__(self):
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x: self.double(x))

    def double(self, v):
        return v * 2

    def work(self, fn):
        self.o.wr(fn(21))


@testbench
def test():
    m = WorkerLambda06()
    wait_value(42, m.o)
    assert m.o.rd() == 42
