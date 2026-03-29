from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import uint32


MASK32 = 0xFFFFFFFF


@module
class MaskTest:
    def __init__(self):
        self.din = Handshake(uint32, "in")
        self.dout = Handshake(uint32, "out")
        self.append_worker(self.main)

    def main(self):
        x = self.din.rd()
        # x is uint32 (unsigned), so >> is logical shift (zero-fill).
        # MASK32 = 0xFFFFFFFF is also uint32 after literal signedness fix.
        result = (x >> 2) & MASK32
        self.dout.wr(result)


@testbench
def test():
    m = MaskTest()
    # 0xefcdab89 = 4023233417 (unsigned)
    m.din.wr(0xefcdab89)
    d = m.dout.rd()
    print(d)
    # Logical right shift: 0xefcdab89 >> 2 = 0x3BF36AE2 = 1005808354
    assert d == 1005808354
