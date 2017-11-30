from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Queue


@module
class M:
    ONE = 1
    TWO = 2
    THREE = 3

    def __init__(self):
        self.out = Queue(int, 'out')
        self.append_worker(self.worker)

    def worker(self):
        while is_worker_running():
            self.out.wr(self.func(1))
            self.out.wr(self.func(2))
            self.out.wr(self.func(3))

    def func(self, v):
        if v == 1:
            return self.ONE
        elif v == 2:
            return self.TWO
        else:
            return self.THREE


@testbench
def test(m):
    d = m.out.rd()
    assert d == M.ONE
    d = m.out.rd()
    assert d == M.TWO
    d = m.out.rd()
    assert d == M.THREE


m = M()
test(m)
