from polyphony import module, timed
from polyphony import testbench
from polyphony.io import Port
from polyphony.timing import clkfence


@timed
@module
class timed01:
    def __init__(self):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out', -1)
        self.append_worker(self.w)

    def w(self):
        # 0
        clkfence()
        # 1
        x = self.i.rd()
        assert 3 == x
        clkfence()
        # 2
        #print(x)  # error
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
    # 0
    m.i.wr(3)
    clkfence()
    # 1
    m.i.wr(6)
    clkfence()
    # 2
    clkfence()
    # 3
    x = m.o.rd()
    assert x == -1
    clkfence()
    # 4
    x = m.o.rd()
    assert x == 10
    clkfence()
    # 5
    clkfence()
    # 6
    assert 20 == m.o.rd()
    clkfence()


m = timed01()
test(m)
