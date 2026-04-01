from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


class Inner:
    def __init__(self, val):
        self.val = val


class Outer:
    def __init__(self, x, y):
        self.a = Inner(x)
        self.b = Inner(y)


@module
class CtorObj04:
    def __init__(self, params):
        self.params = params
        self.o = Port(int, 'out')
        self.append_worker(self.work)

    def work(self):
        self.o.wr(self.params.a.val + self.params.b.val)


@testbench
def test0():
    p = Outer(10, 20)
    m = CtorObj04(p)
    wait_value(30, m.o)
    assert m.o.rd() == 30
