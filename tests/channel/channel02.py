from polyphony import module, testbench
from polyphony import Channel
from polyphony.timing import timed, clktime, wait_value
from polyphony.io import Port
from polyphony.typing import bit8

@timed
@module
class channel02:
    def __init__(self):
        self.done = Port(bool, 'out', False)
        self.c0 = Channel(bit8, 2)
        self.append_worker(self.sender, self.c0)
        self.append_worker(self.receiver, self.c0)

    def sender(self, ch):
        ch.put(0)
        ch.put(1)
        ch.put(257)
        ch.put(258)

    def receiver(self, ch):
        a = ch.get()
        assert a == 0
        a = ch.get()
        assert a == 1
        a = ch.get()
        assert a == 1
        a = ch.get()
        assert a == 2
        self.done.wr(True)


@timed
@testbench
def test(c):
    wait_value(True, c.done)
    assert clktime() == 9


c = channel02()
test(c)
