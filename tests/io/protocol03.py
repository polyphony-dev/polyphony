from polyphony import testbench, module, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clkfence, clksleep


def worker(i1, i2, o1, o2, param):
    while is_worker_running():
        t1 = i1.rd()
        t2 = i2.rd()
        o1.wr(t1 + param)
        o2.wr(t2 + param)


@module
class Protocol03:
    def __init__(self):
        self.i1 = Port(int8, 'in', init=0, protocol='ready_valid')
        self.i2 = Port(int8, 'in', init=0, protocol='ready_valid')
        self.o1 = Port(int8, 'out', init=0, protocol='ready_valid')
        self.o2 = Port(int8, 'out', init=0, protocol='ready_valid')
        t0_0 = Port(int8, 'any', init=0, protocol='ready_valid')
        t0_1 = Port(int8, 'any', init=0, protocol='ready_valid')
        t1_0 = Port(int8, 'any', init=0, protocol='ready_valid')
        t1_1 = Port(int8, 'any', init=0, protocol='ready_valid')
        self.append_worker(worker, self.i1, self.i2, t0_0, t0_1, 1)
        self.append_worker(worker, t0_0, t0_1, t1_0, t1_1, 2)
        self.append_worker(worker, t1_0, t1_1, self.o1, self.o2, 3)


@testbench
def test(p03):
    p03.i1.wr(2)
    p03.i2.wr(2)
    clkfence()
    assert p03.o1.rd() == 2 + 1 + 2 + 3
    assert p03.o2.rd() == 2 + 1 + 2 + 3
    clksleep(10)
    p03.i1.wr(3)
    p03.i2.wr(3)
    clkfence()
    assert p03.o1.rd() == 3 + 1 + 2 + 3
    assert p03.o2.rd() == 3 + 1 + 2 + 3


p03 = Protocol03()
test(p03)
