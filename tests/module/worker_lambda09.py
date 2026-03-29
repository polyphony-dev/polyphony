"""Lambda passed via ctor arg with a constant ctor parameter."""
from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda09:
    def __init__(self, scale):
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x: x * scale)

    def work(self, fn):
        self.o.wr(fn(21))


@testbench
def test():
    m = WorkerLambda09(2)
    wait_value(42, m.o)
    assert m.o.rd() == 42
