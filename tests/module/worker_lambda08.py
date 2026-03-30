"""Lambda with bitwise operations (practical HLS pattern)."""
from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda08:
    def __init__(self):
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x: (x >> 4) & 0xF)

    def work(self, fn):
        self.o.wr(fn(0xAB))


@testbench
def test():
    m = WorkerLambda08()
    wait_value(0xA, m.o)
    assert m.o.rd() == 0xA
