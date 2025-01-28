from polyphony import testbench, module
from polyphony.io import Port


@module
class init01:
    def __init__(self):
        self.p0 = Port(int, 'out', 123)
        self.p1 = Port(int, 'out', 456)


@testbench
def test():
    m = init01()
    assert 123 == m.p0.rd()
    assert 456 == m.p1.rd()
