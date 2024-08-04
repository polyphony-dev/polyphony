from polyphony import module, testbench
from polyphony import Channel as Channel
from polyphony.timing import timed, clktime, wait_value
from polyphony.io import Port


@timed
@module
class channel03:
    def __init__(self):
        self.done = Port(bool, 'out', False)
        self.c0 = Channel(int, 2)
        self.c1 = Channel(int, 2)
        self.append_worker(self.w0)
        self.append_worker(self.w1)

    def w0(self):
        self.c0.put(1)
        a = self.c1.get()
        assert a == 1
        assert clktime() == 6

        self.c0.put(2)
        a = self.c1.get()
        assert a == 4
        assert clktime() == 12

        self.c0.put(3)
        a = self.c1.get()
        assert a == 9
        assert clktime() == 18

        self.done.wr(True)

    def w1(self):
        a = self.c0.get()
        assert a == 1
        self.c1.put(a * a)
        assert clktime() == 4

        a = self.c0.get()
        assert a == 2
        self.c1.put(a * a)
        assert clktime() == 10

        a = self.c0.get()
        assert a == 3
        self.c1.put(a * a)
        assert clktime() == 16


@timed
@testbench
def test():
    c = channel03()
    wait_value(True, c.done)
    assert clktime() == 19
