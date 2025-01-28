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
class flipped02:
    def __init__(self):
        inf = interface()
        self.fp0 = flipped(inf.p0)
        self.fp1 = flipped(inf.p1)
        self.append_worker(self.main, loop=True)

    def main(self):
        x = self.fp1.rd()
        self.fp0.wr(x)


m = flipped02()


@timed
@testbench
def test(m):
    m.fp1.wr(100)
    clkfence()
    clkfence()
    assert 100 == m.fp0.rd()


test(m)
