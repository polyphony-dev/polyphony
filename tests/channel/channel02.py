from polyphony import module, testbench, Channel
from polyphony.timing import clktime, wait_value
from polyphony.io import Port


@module
class channel02:
    def __init__(self):
        self.done = Port(bool, 'out', False)
        c0 = Channel(int)
        c1 = Channel(int)
        self.append_worker(self.w0, c0, c1)
        self.append_worker(self.w1, c0, c1)

    def w0(self, c0, c1):
        c0.put(1)
        a = c1.get()
        assert a == 1

        c0.put(2)
        a = c1.get()
        assert a == 4

        c0.put(3)
        a = c1.get()
        assert a == 9

    def w1(self, c0, c1):
        a = c0.get()
        assert a == 1
        c1.put(a * a)

        a = c0.get()
        assert a == 2
        c1.put(a * a)

        a = c0.get()
        assert a == 3
        c1.put(a * a)

        self.done.wr(True)


@testbench
def test(c):
    wait_value(True, c.done)
    print(clktime())


c = channel02()
test(c)
