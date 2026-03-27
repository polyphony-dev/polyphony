"""
Issue: aliasvar pass incorrectly eliminates list accumulation variable.

When two for-range accumulation loops over different array pairs appear
in the same outer while-loop body, each followed by conditional
upzero-like array updates, the aliasvar pass (pass 67) incorrectly
treats the accumulation variable as an alias and eliminates it,
replacing the result with constant 0.

IR evidence: after compilation, the scope log shows:
  szh#4 is alias     (aliasvar incorrectly removes accumulation result)
  szh#3 = 0          (accumulation collapses to initial value)

Full reproduction with simulation: tests/chstone/adpcm/adpcm_module.py

Note: The generated HDL may cause simulation timeout due to the bug
affecting control flow. Verify with compile-only + IR log check:
  python simu.py -C tests/issues/list_accum_alias.py
  grep "szh#3 = 0" .tmp/top.ListAccumAlias_0.worker_0.log
If the bug is present, szh#3 is replaced with constant 0.
When fixed, szh#3 should reference the accumulation result.
"""
from polyphony import module, testbench
from polyphony.modules import Handshake


@module
class ListAccumAlias:
    def __init__(self):
        self.data_in = Handshake(int, 'in')
        self.data_out = Handshake(int, 'out')
        self.append_worker(self.worker)

    def worker(self):
        bpl = [0] * 2
        dltx = [0] * 2
        bph = [0] * 2
        dhx = [0] * 2

        n = self.data_in.rd()

        al1 = 0
        ah1 = 0

        i = 0
        while i < n:
            xin = self.data_in.rd()

            # === accumulation 1 ===
            szl = 0
            for k in range(2):
                szl += bpl[k] * dltx[k]

            sl = szl + al1
            dlt = xin - sl
            if dlt < 0:
                dlt = -dlt

            # upzero 1
            if dlt == 0:
                for k in range(2):
                    bpl[k] = (255 * bpl[k]) >> 8
            else:
                for k in range(2):
                    if dlt * dltx[k] >= 0:
                        uz = 128
                    else:
                        uz = -128
                    bpl[k] = uz + ((255 * bpl[k]) >> 8)
            dltx[1] = dltx[0]
            dltx[0] = dlt
            al1 = al1 + dlt

            # === accumulation 2 ===
            szh = 0
            for k in range(2):
                szh += bph[k] * dhx[k]

            sh = szh + ah1
            dh = (xin >> 1) - sh
            if dh < 0:
                dh = -dh
            dh = dh + 1

            # upzero 2
            if dh == 0:
                for k in range(2):
                    bph[k] = (255 * bph[k]) >> 8
            else:
                for k in range(2):
                    if dh * dhx[k] >= 0:
                        uz = 128
                    else:
                        uz = -128
                    bph[k] = uz + ((255 * bph[k]) >> 8)
            dhx[1] = dhx[0]
            dhx[0] = dh
            ah1 = ah1 + dh

            self.data_out.wr(szh)
            i = i + 1


@testbench
def test():
    m = ListAccumAlias()
    m.data_in.wr(3)
    m.data_in.wr(100)
    m.data_in.wr(100)
    m.data_in.wr(100)

    # iter 0: arrays all zero => szh = 0
    d = m.data_out.rd()
    print(d)
    assert d == 0

    # iter 1: bph=[128,128], dhx=[dh0,0] => szh = 128*dh0 != 0
    d = m.data_out.rd()
    print(d)
    assert d != 0  # BUG: aliasvar makes szh=0

    d = m.data_out.rd()
    print(d)
