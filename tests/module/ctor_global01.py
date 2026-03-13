from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value

SCALE = 5
OFFSET = 3


@module
class CtorGlobal:
    def __init__(self, factor, base):
        self.o = Port(int, 'out')
        self.append_worker(self.work, factor, base)

    def work(self, factor, base):
        self.o.wr(6 * factor + base)


@testbench
def test0():
    m = CtorGlobal(SCALE, OFFSET)
    wait_value(33, m.o)
    assert m.o.rd() == 33
