"""Two workers each with a different lambda."""
from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda07:
    def __init__(self):
        self.o1 = Port(int, 'out')
        self.o2 = Port(int, 'out')
        self.append_worker(self.work1, lambda x: x * 2)
        self.append_worker(self.work2, lambda x: x + 10)

    def work1(self, fn):
        self.o1.wr(fn(21))

    def work2(self, fn):
        self.o2.wr(fn(21))


@testbench
def test():
    m = WorkerLambda07()
    wait_value(42, m.o1)
    wait_value(31, m.o2)
    assert m.o1.rd() == 42
    assert m.o2.rd() == 31
