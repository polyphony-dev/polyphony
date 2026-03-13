from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value
from polyphony.typing import int8, uint16


@module
class CtorType:
    def __init__(self, t):
        self.o = Port(t, 'out')
        self.append_worker(self.work)

    def work(self):
        self.o.wr(42)


@testbench
def test_int8():
    m = CtorType(int8)
    wait_value(42, m.o)
    assert m.o.rd() == 42


@testbench
def test_uint16():
    m = CtorType(uint16)
    wait_value(42, m.o)
    assert m.o.rd() == 42
