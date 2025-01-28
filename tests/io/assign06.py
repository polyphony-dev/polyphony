from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@module
class assign06:
    def __init__(self, size):
        self.addr = Port(int, 'in')
        self.data = Port(int, 'in')
        self.we = Port(bool, 'in')
        self.q = Port(int, 'out')
        self.mem = [0] * size
        self.addr_latch = 0  # Module class field will always be a register

        self.append_worker(self.main, loop=True)
        self.q.assign(lambda:self.g())

    def g(self):
        return self.f()

    def f(self):
        return self.mem[self.addr_latch]

    @timed
    def main(self):
        if self.we.rd():
            self.mem[self.addr.rd()] = self.data.rd()
        self.addr_latch = self.addr.rd()





@timed
@testbench
def test_ram():
    ram = assign06(10)
    ram.addr.wr(0)
    ram.we.wr(True)
    ram.data.wr(10)
    clkfence()

    ram.addr.wr(1)
    ram.we.wr(True)
    ram.data.wr(11)
    clkfence()

    ram.addr.wr(2)
    ram.we.wr(True)
    ram.data.wr(12)
    clkfence()

    ram.we.wr(False)
    ram.addr.wr(0)
    clkfence()
    clkfence()
    assert 10 == ram.q.rd()

    ram.addr.wr(1)
    clkfence()
    clkfence()
    assert 11 == ram.q.rd()

    ram.addr.wr(2)
    clkfence()
    clkfence()
    assert 12 == ram.q.rd()
