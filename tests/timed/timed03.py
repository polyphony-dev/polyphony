from polyphony import module
from polyphony import testbench
from polyphony import Reg
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@timed
@module
class timed03:
    def __init__(self):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out')
        self.append_worker(self.w)
        # Module instance variables are always registers
        self.y = 0
        self.z = 0

    def w(self):
        clkfence()

        x = self.i.rd()
        assert 3 == x
        clkfence()

        self.y = self.i.rd()
        assert self.i.rd() == 4
        assert self.y == 0
        clkfence()

        self.z = self.i.rd()
        assert self.i.rd() == 5
        assert self.z == 0
        clkfence()

        self.o.wr(self.y + self.z)
        clkfence()



@testbench
@timed
def test():
    m = timed03()
    m.i.wr(3)
    clkfence()

    m.i.wr(4)
    clkfence()

    m.i.wr(5)
    clkfence()

    # m read z
    clkfence()

    # m write to o
    clkfence()

    print(m.o.rd())
    assert 4 + 5 == m.o.rd()
