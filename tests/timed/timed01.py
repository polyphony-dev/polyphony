from polyphony import module, timed
from polyphony import testbench
from polyphony.io import Port
from polyphony.timing import clkfence


@timed
@module
class timed01:
    def __init__(self):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out')
        self.append_worker(self.w)

    def w(self):
        # 0
        clkfence()
        # 1
        x = self.i.rd()
        clkfence()
        # 2
        print(x)
        clkfence()
        # 3
        self.o.wr(10)
        clkfence()
        # 4
        clkfence()
        # 5
        self.o.wr(20)
        clkfence()
        # 6
        clkfence()


@timed
@testbench
def test(m):
    #0
    m.i.wr(3)
    clkfence()
    # 1
    clkfence()
    # 2
    clkfence()
    # 3
    print(m.o.rd())
    clkfence()
    # 4
    print(m.o.rd())
    clkfence()
    # 5
    clkfence()
    # 6
    print(m.o.rd())
    clkfence()


m = timed01()
test(m)
