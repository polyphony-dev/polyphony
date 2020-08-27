from polyphony import testbench
from polyphony import module
from polyphony.timing import timed, clkfence
from polyphony.typing import bit8
from polyphony.io import Handshake


@timed
@module
class worker_with_tuple:
    def __init__(self):
        self.i  = Handshake(bit8, 'in')
        self.o  = Handshake(bit8, 'out')
        self.append_worker(self.worker)
        self.d0 = 0
        self.d1 = 0
        self.tmp = 0

    def func(self, a, b):
        return (a, b)

    def worker(self):
        self.d0 = self.i.rd()
        self.d1 = self.i.rd()
        clkfence()
        t = self.func(self.d0, self.d1)
        a, b = t[0], t[1]
        print(a, b)
        self.tmp = a + b

        self.d0 = self.i.rd()
        self.d1 = self.i.rd()
        clkfence()
        c, d = self.func(self.d0, self.d1)
        print(c, d)
        self.o.wr(self.tmp + c + d)


@testbench
def test(m):
    m.i.wr(1)
    m.i.wr(2)
    m.i.wr(3)
    m.i.wr(4)
    v = m.o.rd()
    print(v)
    assert 1 + 2 + 3 + 4 == v


m = worker_with_tuple()
test(m)
