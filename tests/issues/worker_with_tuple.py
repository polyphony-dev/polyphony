from polyphony import testbench
from polyphony import module
from polyphony.typing import bit8
from polyphony.io import Queue
from polyphony import is_worker_running


@module
class worker_with_tuple:
    def __init__(self):
        self.i  = Queue(bit8, 'in')
        self.o  = Queue(bit8, 'out')
        self.append_worker(self.worker)

    def func(self, a, b):
        return (a, b)

    def worker(self):
        while is_worker_running():
            d0 = self.i.rd()
            d1 = self.i.rd()
            a, b = self.func(d0, d1)
            self.o.wr(a + b)


@testbench
def test(m):
    m.i.wr(1)
    m.i.wr(2)
    assert 1 + 2 == m.o.rd()


m = worker_with_tuple()
test(m)
