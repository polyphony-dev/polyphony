from polyphony import testbench, module
from polyphony.io import Port


@module
class Init01:
    def __init__(self):
        self.p0 = Port(int, 'out', 123)
        self.p1 = Port(int, 'out', 456)


@testbench
def test(m):
    assert 123 == m.p0.rd()
    assert 456 == m.p1.rd()


m = Init01()
test(m)
