from polyphony import testbench, module
from polyphony.io import Port
from polyphony.typing import bit8
from polyphony.timing import wait_until


@module
class wait_until01:
    def __init__(self):
        self.in0  = Port(bit8, 'in')
        self.out0 = Port(bit8, 'out')
        self.v = 0
        self.append_worker(self.main)

    def main(self):
        while True:
            wait_until(lambda: self.in0.rd() == 1)
            self.out0.wr(10)
            wait_until(lambda: self.in0.rd() == 2)
            self.out0.wr(11)


@testbench
def test():
    m = wait_until01()
    m.in0.wr(1)
    wait_until(lambda: m.out0.rd() == 10)
    assert m.out0.rd() == 10
    m.in0.wr(2)
    wait_until(lambda: m.out0.rd() == 11)
    assert m.out0.rd() == 11
