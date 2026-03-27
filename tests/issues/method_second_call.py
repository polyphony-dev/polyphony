"""
Bug: calling the same method twice in a complex control flow can return
wrong results (X in Verilog, 0 in Python sim) for the second call.

Observed in: tests/chstone/motion/motion_module.py
  - decode_motion_vector() called twice (horizontal then vertical)
  - First call returns correct result, second call returns X/0
  - Workaround: inline the method body at call sites

This simplified test does NOT reproduce the bug.
The actual bug requires:
  - Multiple other method calls between the two calls (Get_motion_code, Get_Bits_large)
  - Conditional assignment of one of the arguments (motion_residual)
  - Complex control flow with multiple while loops
"""
from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake


@module
class MethodSecondCall:
    def __init__(self):
        self.din = Handshake(int, "in")
        self.dout = Handshake(int, "out")
        self.append_worker(self.main)

    def compute(self, pred:int, r_size:int, code:int, residual:int) -> int:
        r_size = r_size % 32
        lim = 16 << r_size
        vec = pred

        if code > 0:
            vec = vec + ((code - 1) << r_size) + residual + 1
            if vec >= lim:
                vec = vec - lim - lim
        elif code < 0:
            vec = vec - ((-code - 1) << r_size) - residual - 1
            if vec < -lim:
                vec = vec + lim + lim

        return vec

    def main(self):
        a_pred = self.din.rd()
        a_code = self.din.rd()
        a_resid = self.din.rd()

        b_pred = self.din.rd()
        b_code = self.din.rd()
        b_resid = self.din.rd()

        # First call
        result_a = self.compute(a_pred, 200, a_code, a_resid)
        self.dout.wr(result_a)

        # Second call with different arguments
        result_b = self.compute(b_pred, 200, b_code, b_resid)
        self.dout.wr(result_b)


@testbench
def test():
    m = MethodSecondCall()

    # First call: compute(45, 200, 6, 240) -> should return 1566
    m.din.wr(45)
    m.din.wr(6)
    m.din.wr(240)

    # Second call: compute(103, 200, 0, 0) -> should return 103
    m.din.wr(103)
    m.din.wr(0)
    m.din.wr(0)

    result_a = m.dout.rd()
    print(result_a)
    assert result_a == 1566

    result_b = m.dout.rd()
    print(result_b)
    assert result_b == 103
