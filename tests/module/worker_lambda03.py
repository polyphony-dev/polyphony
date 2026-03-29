from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda03:
    def __init__(self):
        self.scale = 2
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x: x * self.scale)

    def work(self, fn):
        self.o.wr(fn(21))


@testbench
def test():
    m = WorkerLambda03()
    wait_value(42, m.o)
    assert m.o.rd() == 42
