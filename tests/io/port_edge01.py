from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import timed, clkfence


@module
class edge01:
    def __init__(self):
        self.i = Port(bool, 'in')
        self.rising = Port(bool, 'out', False)
        self.falling = Port(bool, 'out', False)
        self.rising_reg = Port(bool, 'out', False)
        self.rising.assign(lambda:self.i.edge(False, True))
        self.falling.assign(lambda:self.i.edge(True, False))
        self.append_worker(self.w)

    @timed
    def w(self):
        self.rising_reg.wr(self.i.edge(False, True))
        clkfence()

        self.rising_reg.wr(self.i.edge(False, True))
        clkfence()

        self.rising_reg.wr(self.i.edge(False, True))
        clkfence()

        self.rising_reg.wr(self.i.edge(False, True))
        clkfence()


m = edge01()


@timed
@testbench
def test(m):
    m.i.wr(False)
    assert m.rising.rd() == False
    assert m.falling.rd() == False
    assert m.rising_reg.rd() == False
    clkfence()

    m.i.wr(True)
    assert m.rising.rd() == False
    assert m.falling.rd() == False
    assert m.rising_reg.rd() == False
    clkfence()

    m.i.wr(False)
    assert m.rising.rd() == True
    assert m.falling.rd() == False
    assert m.rising_reg.rd() == False
    clkfence()

    m.i.wr(True)
    assert m.rising.rd() == False
    assert m.falling.rd() == True
    assert m.rising_reg.rd() == True
    clkfence()


test(m)
