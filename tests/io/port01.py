from polyphony import testbench, module
from polyphony.io import Port
from polyphony.typing import bit8
from polyphony.timing import timed, clkfence


@module
class port01:
    def __init__(self, w):
        self.in0  = Port(bit8, 'in')
        self.out0 = Port(bit8, 'out')
        self.v = 0
        self.w = w
        self.append_worker(self.main)

    @timed
    def main(self):
        # 0
        clkfence()
        # 1
        self.v = self.in0.rd() + self.w
        clkfence()
        # 2
        self.out0.wr(self.v)
        clkfence()
        # 3
        clkfence()
        # 4
        self.out0.wr(self.in0.rd())
        clkfence()
        # 5


@timed
@testbench
def test():
    p01 = port01(222)
    p02 = port01(223)
    # 0
    p01.in0.wr(1)
    p02.in0.wr(1)
    clkfence()
    # 1
    # read from in0 at module
    clkfence()
    # 2
    # write to out0 at module
    clkfence()
    # 3
    print(p01.out0.rd())
    print(p02.out0.rd())
    assert p01.out0.rd() == 223
    assert p02.out0.rd() == 224
    p01.in0.wr(257)
    clkfence()
    # 4
    # read and write at module
    clkfence()
    # 5
    print(p01.out0.rd())
    assert p01.out0.rd() == 1
