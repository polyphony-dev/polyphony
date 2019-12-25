from polyphony import module, testbench
from polyphony import Channel as Channel
from polyphony.timing import timed, clktime, wait_value
from polyphony.io import Port


@timed
@module
class channel02:
    def __init__(self):
        self.done = Port(bool, 'out', False)
        self.c0 = Channel(int, 2)
        self.c1 = Channel(int, 2)
        self.append_worker(self.w0, self.c0, self.c1)
        self.append_worker(w1, self.c0, self.c1)

    def w0(self, c0, c1):
        c0.put(1)
        a = c1.get()
        assert a == 1
        assert clktime() == 6

        c0.put(2)
        a = c1.get()
        assert a == 4
        assert clktime() == 12

        c0.put(3)
        a = c1.get()
        assert a == 9
        assert clktime() == 18

        self.done.wr(True)


@timed
def w1(c0, c1):
    a = c0.get()
    assert a == 1
    c1.put(a * a)
    assert clktime() == 4

    a = c0.get()
    assert a == 2
    c1.put(a * a)
    assert clktime() == 10

    a = c0.get()
    assert a == 3
    c1.put(a * a)
    assert clktime() == 16


@timed
@testbench
def test(c):
    wait_value(True, c.done)
    assert clktime() == 19


c = channel02()
test(c)
