"""
Bug: Pure Python sim (USE_CSIM=0) truncates integer constants wider than
32 bits because visit_AHDL_CONST hardcodes width=32.

Example: 0x000FFFFFFFFFFFFF (52-bit mask) becomes Integer(-1, 32, True)
after masking and twos_comp. Then `x & (-1)` == x, losing the mask effect.

This causes dfdiv and other 64-bit arithmetic to produce wrong results.

Reproduce: USE_CSIM=0 python simu.py -P tests/issues/pysim_const_width.py
"""
from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import bit64

MASK52 = 0x000FFFFFFFFFFFFF


@module
class ConstWidth:
    def __init__(self):
        self.din = Handshake(bit64, "in")
        self.dout = Handshake(bit64, "out")
        self.append_worker(self.main)

    def main(self):
        x = self.din.rd()
        # Construct a 64-bit value with upper bits set
        a:bit64 = x << 48
        # Mask with 52-bit constant: should clear upper 12 bits
        # Bug: MASK52 truncated to -1 in pure Python sim, so result == a
        result:bit64 = a & MASK52
        self.dout.wr(result)


@testbench
def test():
    m = ConstWidth()

    # x=0x1234 → a = 0x1234000000000000
    # result = 0x1234000000000000 & 0x000FFFFFFFFFFFFF = 0x0004000000000000
    m.din.wr(0x1234)
    d = m.dout.rd()
    print(d)
    assert d == 0x0004000000000000
