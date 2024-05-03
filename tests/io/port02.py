from polyphony import testbench, module
from polyphony.io import Port
from polyphony.typing import bit8
from polyphony.timing import timed, clkfence, wait_value


@module
class port02:
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
            self.out0.wr(10)


@testbench
def test():
    p = port02()
    p.in0.wr(1)
    wait_value(10, p.out0)
    p.in0.wr(2)
    print(p.out0.rd())
