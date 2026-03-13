from polyphony import testbench, module
from polyphony.io import connect, Port
from polyphony.timing import timed, wait_value, clkfence
from polyphony.typing import int8



@module
@timed
class Fifo:
    def __init__(self, dtype, capacity):
        self.read = Port(bool, 'in')
        self.dout = Port(dtype, 'out')
        self.empty = Port(bool, 'out')
        self.outv = 0

        self.write = Port(bool, 'in')
        self.din = Port(dtype, 'in')
        self.full = Port(bool, 'out')
            
        self.append_worker(self.worker, loop=True)
        self.append_worker(self.update_flag, loop=True)
        self.length = capacity

        self.mem = [0] * capacity
        self.wp = 0
        self.rp = 0
        self._empty = 1
        self._full = 0

        self.dout.assign(lambda:self.mem[self.rp])
        self.empty.assign(lambda:self._empty == 1)
        self.full.assign(lambda:self._full == 1)

    def rd(self):
        wait_value(False, self.empty)
        self.read.wr(True)
        clkfence()
        self.read.wr(False)
        self.outv = self.dout.rd()
        clkfence()
        return self.outv

    def wr(self, v):
        wait_value(False, self.full)
        self.write.wr(True)
        self.din.wr(v)
        clkfence()
        self.write.wr(False)

    def _inc_rp(self):
        self.rp = 0 if self.rp == (self.length - 1) else self.rp + 1

    def _inc_wp(self):
        self.wp = 0 if self.wp == (self.length - 1) else self.wp + 1

    def worker(self):
        if self.read.rd() and not self._empty:
            self._inc_rp()
        if self.write.rd() and not self._full:
            self._inc_wp()
            self.mem[self.wp] = self.din.rd()

    def update_flag(self):
        if (self.write.rd()
                and not self._full
                and self.wp + 1 == self.rp):
            self._full = 1
        elif self._full and self.wp == self.rp:
            self._full = 1
        else:
            self._full = 0
        if (self.read.rd()
                and not self._empty
                and self.rp + 1 == self.wp):
            self._empty = 1
        elif self._empty and self.wp == self.rp:
            self._empty = 1
        else:
            self._empty = 0
@timed
@testbench
def test():
    f = Fifo(int8, 4)
    f.wr(1)
    f.wr(2)
    f.wr(3)
    f.wr(4)
    assert 1 == f.rd()
    assert 2 == f.rd()
    assert 3 == f.rd()
    assert 4 == f.rd()
    print('test passed')
