from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@module
class ram:
    def __init__(self, size):
        self.addr = Port(int, 'in')
        self.data = Port(int, 'in')
        self.we = Port(bool, 'in')
        self.q = Port(int, 'out')
        self.mem = [0] * size
        self.addr_latch = 0  # Module class field will always be a register

        self.append_worker(self.main, loop=True)
        self.q.assign(self.g)

    def g(self):
        return self.f()

    def f(self):
        return self.mem[self.addr_latch]

    @timed
    def main(self):
        if self.we.rd():
            self.mem[self.addr.rd()] = self.data.rd()
        self.addr_latch = self.addr.rd()


@module
class assign08:
    def __init__(self, size):
        self.r = ram(size)


m = assign08(10)


@timed
@testbench
def test_ram(ram):
    ram.r.addr.wr(0)
    ram.r.we.wr(True)
    ram.r.data.wr(10)
    clkfence()

    ram.r.addr.wr(1)
    ram.r.we.wr(True)
    ram.r.data.wr(11)
    clkfence()

    ram.r.addr.wr(2)
    ram.r.we.wr(True)
    ram.r.data.wr(12)
    clkfence()

    ram.r.we.wr(False)
    ram.r.addr.wr(0)
    clkfence()
    clkfence()
    assert 10 == ram.r.q.rd()

    ram.r.addr.wr(1)
    clkfence()
    clkfence()
    assert 11 == ram.r.q.rd()

    ram.r.addr.wr(2)
    clkfence()
    clkfence()
    assert 12 == ram.r.q.rd()


test_ram(m)
