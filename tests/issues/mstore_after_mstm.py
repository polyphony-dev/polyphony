"""
Issue: mstore scheduled after MStm writes wrong wire value.

When an inner while-loop precedes a delay-line shift (d[1]=d[0]; d[0]=v),
the MStm (loop-carried update of s) and the shift start are merged into
the inner-loop exit state. Over subsequent states of the shift, v (a wire
depending on s) reflects the MStm-updated s rather than the pre-update value.

Trigger conditions (all required):
  - Outer while-loop with a loop-carried variable (s)
  - v depends on s via conditional (if s==0: v=0 else: v=-2)
  - Inner while-loop between v's definition and the mstore
  - Delay-line shift with 2+ elements (d[1]=d[0]; d[0]=v)
"""
from polyphony import module, testbench
from polyphony.modules import Handshake


@module
class M:
    def __init__(self):
        self.i = Handshake(int, 'in')
        self.o = Handshake(int, 'out')
        self.append_worker(self.run)

    def run(self):
        a = [0] * 2
        d = [0] * 2

        n = self.i.rd()
        s = 0
        j = 0
        while j < n:
            x = self.i.rd()
            self.o.wr(d[0])

            # v depends on loop-carried s
            if s == 0:
                v = 0
            else:
                v = -2

            # Inner loop (required to trigger the bug)
            k = 0
            while k < 2:
                a[k] = v
                k = k + 1

            # Delay shift (2+ stages required)
            d[1] = d[0]
            d[0] = v       # BUG: v is a wire, reflects updated s

            # Loop-carried update (becomes MStm)
            s = s + x

            j = j + 1


@testbench
def test():
    m = M()
    m.i.wr(3)

    # iter 0: s=0 → v=0, d[0]=0, s→10
    m.i.wr(10)
    assert m.o.rd() == 0    # d[0] from init

    # iter 1: s=10 → v=-2, d[0] should show iter 0's v=0
    m.i.wr(10)
    d = m.o.rd()
    print(d)
    assert d == 0            # BUG: shows -2

    # iter 2: d[0] from iter 1 = -2
    m.i.wr(10)
    d = m.o.rd()
    print(d)
    assert d == -2
