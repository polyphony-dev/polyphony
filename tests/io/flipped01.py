from polyphony import module, testbench
from polyphony.io import Port, flipped
from polyphony.timing import timed, clkfence


@timed
class interface:
    def __init__(self):
        self.p0 = Port(int, 'in')
        self.p1 = Port(int, 'out')


@timed
@module
class flipped01:
    def __init__(self):
        self.fp = flipped(interface())
        self.append_worker(self.main, loop=True)

    def main(self):
        x = self.fp.p1.rd()
        self.fp.p0.wr(x)


m = flipped01()


@timed
@testbench
def test(m):
    m.fp.p1.wr(100)
    clkfence()
    clkfence()
    assert 100 == m.fp.p0.rd()


test(m)
