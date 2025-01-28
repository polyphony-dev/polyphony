from polyphony import testbench, module, __python__
from polyphony.io import Port
from polyphony.modules import Handshake
from polyphony.typing import int8
from polyphony.timing import timed, clkfence, wait_until, clktime


@timed
@module
class handshake02:
    def __init__(self):
        #self.i = Handshake(int8, 'in')
        self.i_data = Port(int8, 'in')
        self.i_ready = Port(bool, 'out', 0)
        self.i_valid = Port(bool, 'in')

        self.o_data = Port(int8, 'out', init=0)
        self.o_ready = Port(bool, 'in')
        self.o_valid = Port(bool, 'out', 0)

        self.append_worker(self.main)

    def rd(self):
        print(10)
        self.i_ready.wr(True)
        clkfence()
        #print(11)
        wait_until(lambda : self.i_valid.rd() == True)
        #while self.i_valid.rd() is not True:
        #    clkfence()
        self.i_ready.wr(False)
        return self.i_data.rd()

    def wr(self, v):
        print(20, clktime())
        self.o_data.wr(v)
        self.o_valid.wr(True)
        clkfence()
        wait_until(lambda : self.o_ready.rd() == True)
        #while self.o_ready.rd() is not True:
        #    clkfence()
        self.o_valid.wr(False)

    def main(self):
        t = self.rd()
        self.wr(t * t)


@timed
@testbench
def test():
    p01 = handshake02()
    #p01.i.wr(2)
    print(1)
    p01.i_data.wr(2)
    p01.i_valid.wr(1)
    clkfence()
    print(2, clktime())
    wait_until(lambda : p01.i_ready.rd() == 1)
    #while p01.i_ready.rd() != 1:
    #    clkfence()
    print(3, clktime())
    p01.i_valid.wr(0)

    #assert p01.o.rd() == 4
    p01.o_ready.wr(1)
    clkfence()
    print(4)
    wait_until(lambda : p01.o_valid.rd() == 1)
    #while p01.o_valid.rd() != 1:
    #    clkfence()
    p01.o_ready.wr(0)
    assert p01.o_data.rd() == 4
