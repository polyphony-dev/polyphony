from polyphony import testbench, module, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clkfence, clksleep


def worker(i, o, param):
    while is_worker_running():
        t = i.rd()
        o.wr(t + param)


@module
class Protocol03:
    def __init__(self):
        self.i = Port(int8, init=0, protocol='ready_valid')
        self.o = Port(int8, init=0, protocol='ready_valid')
        t0 = Port(int8, init=0, protocol='ready_valid')
        t1 = Port(int8, init=0, protocol='ready_valid')
        self.append_worker(worker, self.i, t0, 1)
        self.append_worker(worker, t0, t1, 2)
        self.append_worker(worker, t1, self.o, 3)


@testbench
def test(p03):
    p03.i.wr(2)
    assert p03.o.rd() == 2 + 1 + 2 + 3
    clksleep(10)
    p03.i.wr(3)
    assert p03.o.rd() == 3 + 1 + 2 + 3


p03 = Protocol03()
test(p03)
