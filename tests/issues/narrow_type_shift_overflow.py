"""
Bug: Literal constants assigned to local variables get narrow inferred types,
causing shift operations to silently overflow to 0.

    zExp = 0x7FF        # inferred as ~11 bits
    result = zExp << 52  # overflows to 0

Workaround: annotate with bit64 type hint.

    zExp:bit64 = 0x7FF
    result = zExp << 52  # correct: 0x7FF0000000000000
"""
from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import bit64

MASK64 = 0xFFFFFFFFFFFFFFFF


@module
class NarrowShift:
    def __init__(self):
        self.din = Handshake(bit64, "in")
        self.dout = Handshake(bit64, "out")
        self.append_worker(self.main)

    def main(self):
        a = self.din.rd()
        zExp = 0x7FF
        result = (zExp << 52) & MASK64
        self.dout.wr(result)


@testbench
def test():
    m = NarrowShift()
    m.din.wr(42)
    result = m.dout.rd()
    assert result == 0x7FF0000000000000
