from polyphony import module, is_worker_running
from polyphony import testbench
from polyphony.timing import timed, clkfence
from polyphony.io import Port


@timed
@module
class field02:
    def __init__(self, size):
        self.size = size
        self.v = [None] * self.size
        self.i = Port(int, 'in')
        self.o = Port(int, 'out')
        self.append_worker(self.writer, loop=True)
        self.append_worker(self.reader, loop=True)
        self.append_worker(self.local_test, loop=True)

    def local_test(self):
        local = [0] * self.size
        assert len(local) == 8
        local[0] = 10
        clkfence()
        assert local[0] == 10

    def reader(self):
        assert len(self.v) == 8
        assert len(self.v) == self.size
        self.o.wr(self.v[0])

    def writer(self):
        self.v[0] = self.i.rd()


m = field02(8)


@timed
@testbench
def test(m):
    m.i.wr(10)
    clkfence()
    clkfence()
    clkfence()
    assert 10 == m.o.rd()

    m.i.wr(20)
    clkfence()
    clkfence()
    clkfence()
    assert 20 == m.o.rd()


test(m)
