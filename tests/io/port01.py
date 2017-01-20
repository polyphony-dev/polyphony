from polyphony import testbench, top
from polyphony.io import Int

@top
class port01:
    def __init__(self, in0, out0):
        self.in0 = in0
        self.out0 = out0        

    @top.thread
    def main(self):
        self.out0(self.in0() * self.in0())

@testbench
def test():
    in0 = Int(8)
    out0 = Int(8)
    in0(2)
    p01 = port01(in0, out0)
    p01.run(10)
    assert out0() == 4

test()

