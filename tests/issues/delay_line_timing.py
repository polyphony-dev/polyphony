"""
Issue: delay line shift writes (arr[0] = val) lag by one iteration
relative to conditional array writes in the same loop body.
"""
from polyphony import module, testbench
from polyphony.modules import Handshake


@module
class DelayLineTiming:
    def __init__(self):
        self.data_in = Handshake(int, 'in')
        self.data_out = Handshake(int, 'out')
        self.append_worker(self.worker)

    def worker(self):
        bph = [0] * 2
        dhx = [0] * 2

        n = self.data_in.rd()

        i = 0
        while i < n:
            val = self.data_in.rd()

            # Output current state
            self.data_out.wr(bph[0])
            self.data_out.wr(dhx[0])

            # Conditional update (like upzero)
            if val != 0:
                bph[0] = 128
                bph[1] = 128
            else:
                bph[0] = (255 * bph[0]) >> 8
                bph[1] = (255 * bph[1]) >> 8

            # Sequential delay line shift
            dhx[1] = dhx[0]
            dhx[0] = val

            i = i + 1


@testbench
def test():
    m = DelayLineTiming()

    # Write n first
    m.data_in.wr(3)

    # iter 0: write val, then read outputs
    m.data_in.wr(42)
    d_bph = m.data_out.rd()
    d_dhx = m.data_out.rd()
    print(d_bph, d_dhx)
    assert d_bph == 0   # bph=[0,0] before update
    assert d_dhx == 0   # dhx=[0,0] before update

    # iter 1: bph=[128,128], dhx=[42,0]
    m.data_in.wr(7)
    d_bph = m.data_out.rd()
    d_dhx = m.data_out.rd()
    print(d_bph, d_dhx)
    assert d_bph == 128
    assert d_dhx == 42

    # iter 2: bph=[128,128], dhx=[7,42]
    m.data_in.wr(0)
    d_bph = m.data_out.rd()
    d_dhx = m.data_out.rd()
    print(d_bph, d_dhx)
    assert d_bph == 128
    assert d_dhx == 7
