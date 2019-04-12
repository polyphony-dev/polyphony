from polyphony import module, testbench, Reg
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@module
class assign05:
    def __init__(self, size):
        self.addr = Port(int, 'in')
        self.data = Port(int, 'in')
        self.we = Port(bool, 'in')
        self.q = Port(int, 'out')
        self.mem = [0] * size

        self.addr_latch = Reg()
        self.append_worker(self.main, loop=True)
        self.q.assign(lambda:self.mem[self.addr_latch.v])

    @timed
    def main(self):
        if self.we.rd():
            self.mem[self.addr.rd()] = self.data.rd()
        self.addr_latch.v = self.addr.rd()


m = assign05(10)


@timed
@testbench
def test_ram(ram):
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
    print(ram.q.rd())

    ram.addr.wr(1)
    clkfence()
    clkfence()
    print(ram.q.rd())

    ram.addr.wr(2)
    clkfence()
    clkfence()
    print(ram.q.rd())


test_ram(m)
