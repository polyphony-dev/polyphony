from polyphony import testbench, module
from polyphony.io import Int


@module
class Protocol01:
    def __init__(self):
        self.i = Int(width=8, init=0, protocol='valid')
        self.o = Int(width=8, init=0, protocol='ready_valid')
        self.append_worker(self.main)

    def main(self):
        # Reading from the "valid" protocol port is blocked until the port becomes 'valid'.
        t = self.i.rd()
        # Writing to the 'ready_valid' protocol port makes the port 'valid'.
        # And if the port is not 'ready', it is blocked until the port becomes 'ready'.
        self.o.wr(t * t)


@testbench
def test(p01):
    # Writing to the 'valid' protocol port makes the port 'valid'.
    # And blocking never happens.
    p01.i.wr(2)
    # Reading from the "ready_valid" protocol port is blocked until the port becomes 'valid'.
    # And if the port becomes 'valid', makes the port 'ready'.
    assert p01.o.rd() == 4


p01 = Protocol01()
test(p01)
