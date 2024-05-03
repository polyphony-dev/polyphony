from polyphony import testbench, module
from polyphony.io import Port
from polyphony.typing import bit8
from polyphony.timing import wait_value


@module
class wait_until02:
    def __init__(self):
        self.in0  = Port(bit8, 'in')
        self.out0 = Port(bit8, 'out')
        self.v = 0
        self.append_worker(self.main)

    def main(self):
        while True:
            wait_value(1, self.in0)
            self.out0.wr(10)
            wait_value(2, self.in0)
            self.out0.wr(11)


@testbench
def test():
    m = wait_until02()
    m.in0.wr(1)
    wait_value(10, m.out0)
    assert m.out0.rd() == 10
    m.in0.wr(2)
    wait_value(11, m.out0)
    assert m.out0.rd() == 11
