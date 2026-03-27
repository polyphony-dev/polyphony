from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class param_tuple:
    def __init__(self, base, offsets):
        self.o = Port(int, 'out')
        self.append_worker(self.work, base, offsets)

    def work(self, base, offsets):
        a, b = offsets
        self.o.wr(base + a + b)


@testbench
def test0():
    m = param_tuple(10, (1, 2))
    wait_value(13, m.o)
    assert m.o.rd() == 13
