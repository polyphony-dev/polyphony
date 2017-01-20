from polyphony import testbench, top
from polyphony.io import Int

@top
class port02:
    INIT = 0
    READ = 1
    WRITE = 2
    DONE = 3
    
    def __init__(self, in0, out0):
        self.in0 = in0
        self.out0 = out0        
        self.state = port02.INIT
        self.tmp = 0

    @top.thread
    def main(self):
        if self.state == port02.INIT:
            self.state = port02.READ
            
        elif self.state == port02.READ:
            self.tmp = self.in0() * self.in0()
            self.state = port02.WRITE

        elif self.state == port02.WRITE:
            self.out0(self.tmp)
            self.state = port02.DONE

        elif self.state == port02.DONE:
            self.state = port02.INIT

@testbench
def test():
    in0 = Int(8)
    out0 = Int(8)
    in0(2)
    p02 = port02(in0, out0)
    p02.run(10)
    assert out0() == 4

test()


