from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


class Params:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.total = x + y


@module
class CtorObj02:
    def __init__(self, params):
        self.params = params
        self.o = Port(int, 'out')
        self.append_worker(self.work)

    def work(self):
        self.o.wr(self.params.x + self.params.y)


@testbench
def test0():
    p = Params(10, 20)
    m = CtorObj02(p)
    wait_value(30, m.o)
    assert m.o.rd() == 30
