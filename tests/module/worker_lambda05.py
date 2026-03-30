from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda05:
    def __init__(self):
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x, y: x + y)

    def work(self, fn):
        self.o.wr(fn(21, 21))


@testbench
def test():
    m = WorkerLambda05()
    wait_value(42, m.o)
    assert m.o.rd() == 42
