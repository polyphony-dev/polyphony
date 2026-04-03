"""Test: user-defined Channel-equivalent module class (no @inlinelib).

This should produce a compile error because the parent module's inlined
methods write to internal fields of the submodule, which cannot be
compiled as a separate Verilog module.
"""
from polyphony import module, testbench
from polyphony.timing import timed, clktime, wait_value, wait_until, clkfence
from polyphony.io import Port
from polyphony.typing import bit8, List


@timed
@module
class MyChannel:
    def __init__(self):
        self.din:bit8 = 0
        self.write = False
        self.read = False
        self.length = 2
        self.mem:List[bit8][2] = [0] * 2
        self.wp = 0
        self.rp = 0
        self.count = 0
        self.append_worker(self.write_worker, loop=True)
        self.append_worker(self.main_worker, loop=True)

    def put(self, v):
        wait_until(lambda: not self.full() and not self.will_full())
        self.write = True
        self.din = v
        clkfence()
        self.write = False

    def get(self):
        wait_until(lambda: not self.empty() and not self.will_empty())
        self.read = True
        clkfence()
        self.read = False
        return self.mem[self.rp]

    def full(self):
        return self.count >= self.length

    def empty(self):
        return self.count == 0

    def will_full(self):
        return self.write and not self.read and self.count == self.length - 1

    def will_empty(self):
        return self.read and not self.write and self.count == 1

    def write_worker(self):
        if self.write:
            self.mem[self.wp] = self.din

    def _inc_wp(self):
        self.wp = 0 if self.wp == self.length - 1 else self.wp + 1

    def _inc_rp(self):
        self.rp = 0 if self.rp == self.length - 1 else self.rp + 1

    def main_worker(self):
        if self.write and self.read:
            if self.count == self.length:
                self.count = self.count - 1
                self._inc_rp()
            elif self.count == 0:
                self.count = self.count + 1
                self._inc_wp()
            else:
                self.count = self.count
                self._inc_wp()
                self._inc_rp()
        elif self.write:
            if self.count < self.length:
                self.count = self.count + 1
                self._inc_wp()
        elif self.read:
            if self.count > 0:
                self.count = self.count - 1
                self._inc_rp()


@timed
@module
class inline_channel01:
    def __init__(self):
        self.done = Port(bool, 'out', False)
        self.c0 = MyChannel()
        self.append_worker(self.sender)
        self.append_worker(self.receiver)

    def sender(self):
        self.c0.put(0)
        self.c0.put(1)
        self.c0.put(257)
        self.c0.put(258)

    def receiver(self):
        a = self.c0.get()
        assert a == 0
        a = self.c0.get()
        assert a == 1
        a = self.c0.get()
        assert a == 1
        a = self.c0.get()
        assert a == 2
        self.done.wr(True)


@timed
@testbench
def test():
    c = inline_channel01()
    wait_value(True, c.done)
    assert clktime() == 9
