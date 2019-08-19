from polyphony import testbench, module
from polyphony.io import Handshake
from polyphony.typing import int8
from polyphony.timing import timed


@module
class handshake01:
    def __init__(self):
        self.i = Handshake(int8, 'in')
        self.o = Handshake(int8, 'out', init=0)
        self.append_worker(self.main)

    @timed
    def main(self):
        t = self.i.rd()
        self.o.wr(t * t)


@timed
@testbench
def test(p01):
    p01.i.wr(2)
    assert p01.o.rd() == 4


p01 = handshake01()
test(p01)
