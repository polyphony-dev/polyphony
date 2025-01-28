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
class flipped03:
    def __init__(self):
        inf = interface()
        self.p = flipped(flipped(inf))
        self.fp = flipped(inf)
        self.append_worker(self.main, loop=True)

    def main(self):
        x = self.p.p0.rd()
        y = self.fp.p1.rd()
        self.p.p1.wr(x)
        self.fp.p0.wr(y)


m = flipped03()


@timed
@testbench
def test(m):
    m.p.p0.wr(100)
    m.fp.p1.wr(200)
    clkfence()
    clkfence()
    assert 100 == m.p.p1.rd()
    assert 200 == m.fp.p0.rd()


test(m)
