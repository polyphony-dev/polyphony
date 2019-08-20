from polyphony import module, testbench, Channel
from polyphony.timing import clktime, wait_value
from polyphony.io import Port


@module
class channel01:
    def __init__(self):
        self.done = Port(bool, 'out', False)
        self.c0 = Channel(int)
        self.append_worker(self.sender)
        self.append_worker(self.receiver)

    def sender(self):
        self.c0.put(0)
        self.c0.put(1)
        self.c0.put(2)
        self.c0.put(3)

    def receiver(self):
        a = self.c0.get()
        assert a == 0
        a = self.c0.get()
        assert a == 1
        a = self.c0.get()
        assert a == 2
        a = self.c0.get()
        assert a == 3
        self.done.wr(True)


@testbench
def test(c):
    wait_value(True, c.done)
    print(clktime())


c = channel01()
test(c)
