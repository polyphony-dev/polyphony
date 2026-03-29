from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake


MASK32 = 0xFFFFFFFF


@module
class MaskTest:
    def __init__(self):
        self.din = Handshake(int, "in")
        self.dout = Handshake(int, "out")
        self.append_worker(self.main)

    def main(self):
        x = self.din.rd()
        # Unsigned right shift by 2, masked to 32 bits.
        # For x = 0xefcdab89 (signed: -271733879):
        #   Arithmetic >> 2 gives 0xFBF36AE2 (sign-extended)
        #   Expected logical >> 2: 0x3BF36AE2
        #   & 0xFFFFFFFF should clear sign bits but doesn't work
        #   because 0xFFFFFFFF is typed as -1 in signed 32-bit.
        result = (x >> 2) & MASK32
        self.dout.wr(result)


@testbench
def test():
    m = MaskTest()
    # 0xefcdab89 as signed 32-bit = -271733879
    m.din.wr(-271733879)
    d = m.dout.rd()
    print(d)
    # Expected: logical right shift gives 0x3BF36AE2 = 1005808354
    # Actual bug: gives 0xFBF36AE2 = -67933470 (arithmetic shift, mask is no-op)
    assert d == 1005808354
