"""
Bug: Pure Python sim (USE_CSIM=0) crashes with ZeroDivisionError when
combinational nets include a floor division whose divisor depends on
a value only available in certain states.

Root cause: _eval_decls() evaluates ALL combinational assignments every
cycle, including state-conditional ones. When the state machine is not
in the state that computes the divisor, the divisor net retains its
initial value of 0, causing ZeroDivisionError.

csim and HDL sim do not have this issue.

Reproduce: USE_CSIM=0 python simu.py -P tests/issues/pysim_zerodiv.py
"""
from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import bit64


@module
class DivByShifted:
    def __init__(self):
        self.din = Handshake(bit64, "in")
        self.dout = Handshake(bit64, "out")
        self.append_worker(self.main)

    def main(self):
        x = self.din.rd()
        # Compute large value internally (avoids testbench constant truncation)
        a:bit64 = x << 48  # e.g. x=1 → 0x0001000000000000
        # b = upper 32 bits of a
        b:bit64 = a >> 32   # 0x00010000
        # Bug: before din.rd() completes, a = 0, b = 0, division crashes
        result:bit64 = a // b
        self.dout.wr(result)


@testbench
def test():
    m = DivByShifted()

    # x=1 → a = 1<<48, b = 1<<16, result = 1<<32
    m.din.wr(1)
    d = m.dout.rd()
    print(d)
    assert d == 0x100000000
