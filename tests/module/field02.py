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
        self.append_worker(self.writer)
        self.append_worker(self.reader)

    def reader(self):
        assert len(self.v) == 16
        assert len(self.v) == self.size
        local = [None] * self.size
        assert len(local) == 16
        while is_worker_running():
            self.o.wr(self.v[0])
            clkfence()

    def writer(self):
        while is_worker_running():
            self.v[0] = self.i.rd()
            clkfence()


m = field02(16)


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
