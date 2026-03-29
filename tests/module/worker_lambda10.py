"""Lambda with nested arithmetic (multi-step expression)."""
from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda10:
    def __init__(self):
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x, y: (x + y) * 2 - 1)

    def work(self, fn):
        self.o.wr(fn(10, 11))


@testbench
def test():
    m = WorkerLambda10()
    wait_value(41, m.o)
    assert m.o.rd() == 41
