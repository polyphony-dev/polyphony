from polyphony import testbench, module
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clkfence

@module
class Protocol02:
    def __init__(self):
        self.i = Port(int8, init=0, protocol='ready_valid')
        self.o = Port(int8, init=0, protocol='ready_valid')
        self.append_worker(self.main)

    def main(self):
        t = self.i.rd()
        self.o.wr(t * t)


@testbench
def test(p02):
    p02.i.wr(2)
    clkfence()
    assert p02.o() == 4


p02 = Protocol02()
test(p02)
