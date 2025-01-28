from polyphony import module, testbench
from polyphony import Channel
from polyphony.timing import timed, clktime, wait_value
from polyphony.io import Port
from polyphony.typing import bit8

@timed
@module
class channel01:
    def __init__(self):
        self.done = Port(bool, 'out', False)
        self.c0 = Channel(bit8, 2)
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
    c = channel01()
    wait_value(True, c.done)
    assert clktime() == 9
