from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class CtorTuple:
    def __init__(self, params):
        self.o = Port(int, 'out')
        self.append_worker(self.work, params)

    def work(self, params):
        a, b = params
        self.o.wr(a + b)


@testbench
def test0():
    m = CtorTuple((10, 20))
    wait_value(30, m.o)
    assert m.o.rd() == 30
