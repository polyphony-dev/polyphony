from polyphony import module, testbench
from polyphony.io import Port, flipped
from polyphony.timing import timed, clkfence


@timed
class sub_interface:
    def __init__(self):
        self.p0 = Port(int, 'in')
        self.p1 = Port(int, 'out')


@timed
class interface:
    def __init__(self):
        self.sub0 = sub_interface()


@timed
@module
class flipped04:
    def __init__(self):
        inf = interface()
        self.fp = flipped(inf.sub0)
        self.append_worker(self.main, loop=True)

    def main(self):
        x = self.fp.p1.rd()
        self.fp.p0.wr(x)


m = flipped04()


@timed
@testbench
def test(m):
    m.fp.p1.wr(200)
    clkfence()
    clkfence()
    assert 200 == m.fp.p0.rd()


test(m)
