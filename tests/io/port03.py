from polyphony import testbench, top
from polyphony.io import Bit

@top
class port01:
    def __init__(self, in0, in1, out0):
        self.in0 = in0
        self.in1 = in1
        self.out0 = out0

    @top.thread
    def main(self):
        self.out0(self.in0() & self.in1())

@testbench
def test():
    in0 = Bit()
    in1 = Bit()
    out0 = Bit()
    p01 = port01(in0, in1, out0)

    in0(0)
    in1(0)
    p01.run(10)
    assert out0() == 0

    in0(0)
    in1(1)
    p01.run(10)
    assert out0() == 0

    in0(1)
    in1(0)
    p01.run(10)
    assert out0() == 0

    in0(1)
    in1(1)
    p01.run(10)
    assert out0() == 1

test()

