# +--------------------------------------------------------------------------+
# | CHStone : a suite of benchmark programs for C-based High-Level Synthesis |
# | ======================================================================== |
# |                                                                          |
# | * Collected and Modified : Y. Hara, H. Tomiyama, S. Honda,               |
# |                            H. Takada and K. Ishii                        |
# |                            Nagoya University, Japan                      |
# |                                                                          |
# | * Remark :                                                               |
# |    1. This source code is modified to unify the formats of the benchmark |
# |       programs in CHStone.                                               |
# |    2. Test vectors are added for CHStone.                                |
# |    3. If "main_result" is 0 at the end of the program, the program is    |
# |       correctly executed.                                                |
# |    4. Please follow the copyright of each benchmark program.             |
# +--------------------------------------------------------------------------+

from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake


SIZE = 100
IN_END = 100


@module
class ADPCM:
    def __init__(self):
        self.data_in = Handshake(int, "in")
        self.data_out = Handshake(int, "out")
        self.append_worker(self.adpcm_main)

    def adpcm_main(self):
        # QMF filter coefficients
        h = [
              12,   -44,  -44,   212,    48, -624,   128, 1448,
            -840, -3220, 3804, 15504, 15504, 3804, -3220, -840,
            1448,   128, -624,    48,   212,  -44,   -44,   12
        ]

        qq4_code4_table = [
                0, -20456, -12896, -8968, -6288, -4240, -2584, -1200,
            20456,  12896,   8968,  6288,  4240,  2584,  1200,     0
        ]

        qq6_code6_table = [
              -136,   -136,   -136,   -136, -24808, -21904, -19008, -16704,
            -14984, -13512, -12280, -11192, -10232,  -9360,  -8576,  -7856,
             -7192,  -6576,  -6000,  -5456,  -4944,  -4464,  -4008,  -3576,
             -3168,  -2776,  -2400,  -2032,  -1688,  -1360,  -1040,   -728,
             24808,  21904,  19008,  16704,  14984,  13512,  12280,  11192,
             10232,   9360,   8576,   7856,   7192,   6576,   6000,   5456,
              4944,   4464,   4008,   3576,   3168,   2776,   2400,   2032,
              1688,   1360,   1040,    728,    432,    136,   -432,   -136
        ]

        wl_code_table = [
             -60, 3042, 1198, 538, 334, 172,  58, -30,
            3042, 1198, 538,  334, 172,  58, -30, -60
        ]

        ilb_table = [
            2048, 2093, 2139, 2186, 2233, 2282, 2332, 2383,
            2435, 2489, 2543, 2599, 2656, 2714, 2774, 2834,
            2896, 2960, 3025, 3091, 3158, 3228, 3298, 3371,
            3444, 3520, 3597, 3676, 3756, 3838, 3922, 4008
        ]

        decis_levl = [
              280,   576,   880,  1200,  1520,  1864,  2208,  2584,
             2960,  3376,  3784,  4240,  4696,  5200,  5712,  6288,
             6864,  7520,  8184,  8968,  9752, 10712, 11664, 12896,
            14120, 15840, 17560, 20456, 23352, 32767
        ]

        quant26bt_pos = [
            61, 60, 59, 58, 57, 56, 55, 54,
            53, 52, 51, 50, 49, 48, 47, 46,
            45, 44, 43, 42, 41, 40, 39, 38,
            37, 36, 35, 34, 33, 32, 32
        ]

        quant26bt_neg = [
            63, 62, 31, 30, 29, 28, 27, 26,
            25, 24, 23, 22, 21, 20, 19, 18,
            17, 16, 15, 14, 13, 12, 11, 10,
             9,  8,  7,  6,  5,  4, 4
        ]

        qq2_code2_table = [
            -7408, -1616, 7408, 1616
        ]

        wh_code_table = [
            798, -214, 798, -214
        ]

        # Mutable state - transmit QMF
        tqmf = [0] * 24

        # Encoder state - lower sub-band
        al1 = 0
        al2 = 0
        plt1 = 0
        plt2 = 0
        rlt1 = 0
        rlt2 = 0
        nbl = 0
        detl = 32

        delay_bpl = [0] * 6
        delay_dltx = [0] * 6

        # Encoder state - higher sub-band
        ah1 = 0
        ah2 = 0
        ph1 = 0
        ph2 = 0
        rh1 = 0
        rh2 = 0
        nbh = 0
        deth = 8

        delay_bph = [0] * 6
        delay_dhx = [0] * 6

        # Decoder state - lower sub-band
        dec_al1 = 0
        dec_al2 = 0
        dec_plt1 = 0
        dec_plt2 = 0
        dec_rlt1 = 0
        dec_rlt2 = 0
        dec_nbl = 0
        dec_detl = 32

        dec_del_bpl = [0] * 6
        dec_del_dltx = [0] * 6

        # Decoder state - higher sub-band
        dec_ah1 = 0
        dec_ah2 = 0
        dec_ph1 = 0
        dec_ph2 = 0
        dec_rh1 = 0
        dec_rh2 = 0
        dec_nbh = 0
        dec_deth = 8

        dec_del_bph = [0] * 6
        dec_del_dhx = [0] * 6

        # Receive QMF state
        accumc = [0] * 11
        accumd = [0] * 11

        # Read input data
        test_input = [0] * IN_END
        i = 0
        while i < IN_END:
            test_input[i] = self.data_in.rd()
            i = i + 1

        # Working arrays
        compressed = [0] * (IN_END // 2)

        # il is shared between encode loop and decode loop
        il = 0

        # ============================================================
        # ENCODE loop
        # ============================================================
        i = 0
        while i < IN_END:
            xin1 = test_input[i]
            xin2 = test_input[i + 1]

            # QMF: main multiply accumulate loop
            xa = 0
            xb = 0
            j = 0
            while j < 24:
                xa += tqmf[j] * h[j]
                xb += tqmf[j + 1] * h[j + 1]
                j = j + 2

            # update delay line tqmf
            j = 23
            while j > 1:
                tqmf[j] = tqmf[j - 2]
                j = j - 1
            tqmf[1] = xin1
            tqmf[0] = xin2

            # scale outputs
            xl = (xa + xb) >> 15
            xh = (xa - xb) >> 15

            # --- Lower sub-band encoder ---

            # filtez(delay_bpl, delay_dltx)
            szl = (delay_bpl[0] * delay_dltx[0] + delay_bpl[1] * delay_dltx[1] + delay_bpl[2] * delay_dltx[2] + delay_bpl[3] * delay_dltx[3] + delay_bpl[4] * delay_dltx[4] + delay_bpl[5] * delay_dltx[5]) >> 14

            # filtep(rlt1, al1, rlt2, al2)
            spl = 2 * rlt1
            spl = al1 * spl
            spl2 = 2 * rlt2
            spl = (spl + al2 * spl2) >> 15

            sl = szl + spl
            el = xl - sl

            # quantl(el, detl)
            q_wd = el
            if q_wd < 0:
                q_wd = -q_wd
            mil = 0
            while mil < 30:
                q_decis = (decis_levl[mil] * detl) >> 15
                if q_wd <= q_decis:
                    break
                mil = mil + 1
            if el >= 0:
                il = quant26bt_pos[mil]
            else:
                il = quant26bt_neg[mil]

            dlt = (detl * qq4_code4_table[il >> 2]) >> 15

            # logscl(il, nbl)
            wd = (nbl * 127) >> 7
            nbl = wd + wl_code_table[il >> 2]
            if nbl < 0:
                nbl = 0
            if nbl > 18432:
                nbl = 18432

            # scalel(nbl, 8)
            wd1 = (nbl >> 6) & 31
            wd2 = nbl >> 11
            detl = (ilb_table[wd1] >> (9 - wd2)) << 3

            plt = dlt + szl

            # upzero(dlt, delay_dltx, delay_bpl)
            if dlt == 0:
                k = 0
                while k < 6:
                    delay_bpl[k] = ((255 * delay_bpl[k]) >> 8)
                    k = k + 1
            else:
                k = 0
                while k < 6:
                    if dlt * delay_dltx[k] >= 0:
                        uz_wd2 = 128
                    else:
                        uz_wd2 = -128
                    delay_bpl[k] = uz_wd2 + ((255 * delay_bpl[k]) >> 8)
                    k = k + 1
            delay_dltx[5] = delay_dltx[4]
            delay_dltx[4] = delay_dltx[3]
            delay_dltx[3] = delay_dltx[2]
            delay_dltx[2] = delay_dltx[1]
            delay_dltx[1] = delay_dltx[0]
            delay_dltx[0] = dlt

            # uppol2(al1, al2, plt, plt1, plt2)
            up_wd2 = 4 * al1
            if plt * plt1 >= 0:
                up_wd2 = -up_wd2
            up_wd2 = up_wd2 >> 7
            if plt * plt2 >= 0:
                up_wd4 = up_wd2 + 128
            else:
                up_wd4 = up_wd2 - 128
            apl2 = up_wd4 + (127 * al2 >> 7)
            if apl2 > 12288:
                apl2 = 12288
            if apl2 < -12288:
                apl2 = -12288
            al2 = apl2

            # uppol1(al1, al2, plt, plt1)
            up_wd2 = (al1 * 255) >> 8
            if plt * plt1 >= 0:
                apl1 = up_wd2 + 192
            else:
                apl1 = up_wd2 - 192
            up_wd3 = 15360 - al2
            if apl1 > up_wd3:
                apl1 = up_wd3
            if apl1 < -up_wd3:
                apl1 = -up_wd3
            al1 = apl1

            rlt = sl + dlt

            rlt2 = rlt1
            rlt1 = rlt
            plt2 = plt1
            plt1 = plt

            # --- Higher sub-band encoder ---

            # filtez(delay_bph, delay_dhx)
            szh = (delay_bph[0] * delay_dhx[0] + delay_bph[1] * delay_dhx[1] + delay_bph[2] * delay_dhx[2] + delay_bph[3] * delay_dhx[3] + delay_bph[4] * delay_dhx[4] + delay_bph[5] * delay_dhx[5]) >> 14

            # filtep(rh1, ah1, rh2, ah2)
            sph = 2 * rh1
            sph = ah1 * sph
            sph2 = 2 * rh2
            sph = (sph + ah2 * sph2) >> 15

            sh = sph + szh
            eh = xh - sh

            if eh >= 0:
                ih = 3
            else:
                ih = 1
            decis = (564 * deth) >> 12
            abs_eh = eh
            if eh < 0:
                abs_eh = -eh
            if abs_eh > decis:
                ih = ih - 1


            dh = (deth * qq2_code2_table[ih]) >> 15

            # logsch(ih, nbh)
            wd = (nbh * 127) >> 7
            nbh = wd + wh_code_table[ih]
            if nbh < 0:
                nbh = 0
            if nbh > 22528:
                nbh = 22528

            # scalel(nbh, 10)
            wd1 = (nbh >> 6) & 31
            wd2 = nbh >> 11
            deth = (ilb_table[wd1] >> (11 - wd2)) << 3

            ph = dh + szh

            # upzero(dh, delay_dhx, delay_bph)
            if dh == 0:
                k = 0
                while k < 6:
                    delay_bph[k] = ((255 * delay_bph[k]) >> 8)
                    k = k + 1
            else:
                k = 0
                while k < 6:
                    if dh * delay_dhx[k] >= 0:
                        uz_wd2 = 128
                    else:
                        uz_wd2 = -128
                    delay_bph[k] = uz_wd2 + ((255 * delay_bph[k]) >> 8)
                    k = k + 1
            delay_dhx[5] = delay_dhx[4]
            delay_dhx[4] = delay_dhx[3]
            delay_dhx[3] = delay_dhx[2]
            delay_dhx[2] = delay_dhx[1]
            delay_dhx[1] = delay_dhx[0]
            delay_dhx[0] = dh

            # uppol2(ah1, ah2, ph, ph1, ph2)
            up_wd2 = 4 * ah1
            if ph * ph1 >= 0:
                up_wd2 = -up_wd2
            up_wd2 = up_wd2 >> 7
            if ph * ph2 >= 0:
                up_wd4 = up_wd2 + 128
            else:
                up_wd4 = up_wd2 - 128
            apl2 = up_wd4 + (127 * ah2 >> 7)
            if apl2 > 12288:
                apl2 = 12288
            if apl2 < -12288:
                apl2 = -12288
            ah2 = apl2

            # uppol1(ah1, ah2, ph, ph1)
            up_wd2 = (ah1 * 255) >> 8
            if ph * ph1 >= 0:
                apl1 = up_wd2 + 192
            else:
                apl1 = up_wd2 - 192
            up_wd3 = 15360 - ah2
            if apl1 > up_wd3:
                apl1 = up_wd3
            if apl1 < -up_wd3:
                apl1 = -up_wd3
            ah1 = apl1

            yh = sh + dh

            rh2 = rh1
            rh1 = yh
            ph2 = ph1
            ph1 = ph

            compressed[i // 2] = il | (ih << 6)

            i = i + 2

        # ============================================================
        # DECODE loop
        # ============================================================
        result = [0] * IN_END
        i = 0
        while i < IN_END:
            input_val = compressed[i // 2]

            ilr = input_val & 0x3f
            ih = input_val >> 6

            # --- Lower sub-band decoder ---

            # filtez(dec_del_bpl, dec_del_dltx)
            dec_szl = (dec_del_bpl[0] * dec_del_dltx[0] + dec_del_bpl[1] * dec_del_dltx[1] + dec_del_bpl[2] * dec_del_dltx[2] + dec_del_bpl[3] * dec_del_dltx[3] + dec_del_bpl[4] * dec_del_dltx[4] + dec_del_bpl[5] * dec_del_dltx[5]) >> 14

            # filtep(dec_rlt1, dec_al1, dec_rlt2, dec_al2)
            dec_spl = 2 * dec_rlt1
            dec_spl = dec_al1 * dec_spl
            dec_spl2 = 2 * dec_rlt2
            dec_spl = (dec_spl + dec_al2 * dec_spl2) >> 15

            dec_sl = dec_spl + dec_szl

            dec_dlt = (dec_detl * qq4_code4_table[ilr >> 2]) >> 15
            dl = (dec_detl * qq6_code6_table[il]) >> 15

            rl = dl + dec_sl

            # logscl(ilr, dec_nbl)
            wd = (dec_nbl * 127) >> 7
            dec_nbl = wd + wl_code_table[ilr >> 2]
            if dec_nbl < 0:
                dec_nbl = 0
            if dec_nbl > 18432:
                dec_nbl = 18432

            # scalel(dec_nbl, 8)
            wd1 = (dec_nbl >> 6) & 31
            wd2 = dec_nbl >> 11
            dec_detl = (ilb_table[wd1] >> (9 - wd2)) << 3

            dec_plt = dec_dlt + dec_szl

            # upzero(dec_dlt, dec_del_dltx, dec_del_bpl)
            if dec_dlt == 0:
                k = 0
                while k < 6:
                    dec_del_bpl[k] = ((255 * dec_del_bpl[k]) >> 8)
                    k = k + 1
            else:
                k = 0
                while k < 6:
                    if dec_dlt * dec_del_dltx[k] >= 0:
                        uz_wd2 = 128
                    else:
                        uz_wd2 = -128
                    dec_del_bpl[k] = uz_wd2 + ((255 * dec_del_bpl[k]) >> 8)
                    k = k + 1
            dec_del_dltx[5] = dec_del_dltx[4]
            dec_del_dltx[4] = dec_del_dltx[3]
            dec_del_dltx[3] = dec_del_dltx[2]
            dec_del_dltx[2] = dec_del_dltx[1]
            dec_del_dltx[1] = dec_del_dltx[0]
            dec_del_dltx[0] = dec_dlt

            # uppol2(dec_al1, dec_al2, dec_plt, dec_plt1, dec_plt2)
            up_wd2 = 4 * dec_al1
            if dec_plt * dec_plt1 >= 0:
                up_wd2 = -up_wd2
            up_wd2 = up_wd2 >> 7
            if dec_plt * dec_plt2 >= 0:
                up_wd4 = up_wd2 + 128
            else:
                up_wd4 = up_wd2 - 128
            apl2 = up_wd4 + (127 * dec_al2 >> 7)
            if apl2 > 12288:
                apl2 = 12288
            if apl2 < -12288:
                apl2 = -12288
            dec_al2 = apl2

            # uppol1(dec_al1, dec_al2, dec_plt, dec_plt1)
            up_wd2 = (dec_al1 * 255) >> 8
            if dec_plt * dec_plt1 >= 0:
                apl1 = up_wd2 + 192
            else:
                apl1 = up_wd2 - 192
            up_wd3 = 15360 - dec_al2
            if apl1 > up_wd3:
                apl1 = up_wd3
            if apl1 < -up_wd3:
                apl1 = -up_wd3
            dec_al1 = apl1

            dec_rlt = dec_sl + dec_dlt

            dec_rlt2 = dec_rlt1
            dec_rlt1 = dec_rlt
            dec_plt2 = dec_plt1
            dec_plt1 = dec_plt

            # --- Higher sub-band decoder ---

            # filtez(dec_del_bph, dec_del_dhx)
            dec_szh = (dec_del_bph[0] * dec_del_dhx[0] + dec_del_bph[1] * dec_del_dhx[1] + dec_del_bph[2] * dec_del_dhx[2] + dec_del_bph[3] * dec_del_dhx[3] + dec_del_bph[4] * dec_del_dhx[4] + dec_del_bph[5] * dec_del_dhx[5]) >> 14

            # filtep(dec_rh1, dec_ah1, dec_rh2, dec_ah2)
            dec_sph = 2 * dec_rh1
            dec_sph = dec_ah1 * dec_sph
            dec_sph2 = 2 * dec_rh2
            dec_sph = (dec_sph + dec_ah2 * dec_sph2) >> 15

            dec_sh = dec_sph + dec_szh

            dec_dh = (dec_deth * qq2_code2_table[ih]) >> 15

            # logsch(ih, dec_nbh)
            wd = (dec_nbh * 127) >> 7
            dec_nbh = wd + wh_code_table[ih]
            if dec_nbh < 0:
                dec_nbh = 0
            if dec_nbh > 22528:
                dec_nbh = 22528

            # scalel(dec_nbh, 10)
            wd1 = (dec_nbh >> 6) & 31
            wd2 = dec_nbh >> 11
            dec_deth = (ilb_table[wd1] >> (11 - wd2)) << 3

            dec_ph = dec_dh + dec_szh

            # upzero(dec_dh, dec_del_dhx, dec_del_bph)
            if dec_dh == 0:
                k = 0
                while k < 6:
                    dec_del_bph[k] = ((255 * dec_del_bph[k]) >> 8)
                    k = k + 1
            else:
                k = 0
                while k < 6:
                    if dec_dh * dec_del_dhx[k] >= 0:
                        uz_wd2 = 128
                    else:
                        uz_wd2 = -128
                    dec_del_bph[k] = uz_wd2 + ((255 * dec_del_bph[k]) >> 8)
                    k = k + 1
            dec_del_dhx[5] = dec_del_dhx[4]
            dec_del_dhx[4] = dec_del_dhx[3]
            dec_del_dhx[3] = dec_del_dhx[2]
            dec_del_dhx[2] = dec_del_dhx[1]
            dec_del_dhx[1] = dec_del_dhx[0]
            dec_del_dhx[0] = dec_dh

            # uppol2(dec_ah1, dec_ah2, dec_ph, dec_ph1, dec_ph2)
            up_wd2 = 4 * dec_ah1
            if dec_ph * dec_ph1 >= 0:
                up_wd2 = -up_wd2
            up_wd2 = up_wd2 >> 7
            if dec_ph * dec_ph2 >= 0:
                up_wd4 = up_wd2 + 128
            else:
                up_wd4 = up_wd2 - 128
            apl2 = up_wd4 + (127 * dec_ah2 >> 7)
            if apl2 > 12288:
                apl2 = 12288
            if apl2 < -12288:
                apl2 = -12288
            dec_ah2 = apl2

            # uppol1(dec_ah1, dec_ah2, dec_ph, dec_ph1)
            up_wd2 = (dec_ah1 * 255) >> 8
            if dec_ph * dec_ph1 >= 0:
                apl1 = up_wd2 + 192
            else:
                apl1 = up_wd2 - 192
            up_wd3 = 15360 - dec_ah2
            if apl1 > up_wd3:
                apl1 = up_wd3
            if apl1 < -up_wd3:
                apl1 = -up_wd3
            dec_ah1 = apl1

            rh = dec_sh + dec_dh

            dec_rh2 = dec_rh1
            dec_rh1 = rh
            dec_ph2 = dec_ph1
            dec_ph1 = dec_ph

            # receive quadrature mirror filters
            xd = rl - rh
            xs = rl + rh

            xa1 = xd * h[0]
            xa2 = xs * h[1]

            k = 0
            while k < 10:
                xa1 += accumc[k] * h[k * 2 + 2]
                xa2 += accumd[k] * h[k * 2 + 3]
                k = k + 1
            xa1 += accumc[10] * h[22]
            xa2 += accumd[10] * h[23]

            xout1 = xa1 >> 14
            xout2 = xa2 >> 14

            k = 10
            while k > 0:
                accumc[k] = accumc[k - 1]
                accumd[k] = accumd[k - 1]
                k = k - 1
            accumc[0] = xd
            accumd[0] = xs

            result[i] = xout1
            result[i + 1] = xout2

            i = i + 2

        # Output compressed data (50 values)
        i = 0
        while i < IN_END // 2:
            self.data_out.wr(compressed[i])
            i = i + 1

        # Output result data (100 values)
        i = 0
        while i < IN_END:
            self.data_out.wr(result[i])
            i = i + 1


@testbench
def test():
    adpcm = ADPCM()

    test_data = [
        0x44, 0x44, 0x44, 0x44, 0x44,
        0x44, 0x44, 0x44, 0x44, 0x44,
        0x44, 0x44, 0x44, 0x44, 0x44,
        0x44, 0x44, 0x43, 0x43, 0x43,
        0x43, 0x43, 0x43, 0x43, 0x42,
        0x42, 0x42, 0x42, 0x42, 0x42,
        0x41, 0x41, 0x41, 0x41, 0x41,
        0x40, 0x40, 0x40, 0x40, 0x40,
        0x40, 0x40, 0x40, 0x3f, 0x3f,
        0x3f, 0x3f, 0x3f, 0x3e, 0x3e,
        0x3e, 0x3e, 0x3e, 0x3e, 0x3d,
        0x3d, 0x3d, 0x3d, 0x3d, 0x3d,
        0x3c, 0x3c, 0x3c, 0x3c, 0x3c,
        0x3c, 0x3c, 0x3c, 0x3c, 0x3b,
        0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
        0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
        0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
        0x3b, 0x3b, 0x3b, 0x3b, 0x3b,
        0x3b, 0x3b, 0x3c, 0x3c, 0x3c,
        0x3c, 0x3c, 0x3c, 0x3c, 0x3c
    ]

    test_compressed = [
        0xfd, 0xde, 0x77, 0xba, 0xf2,
        0x90, 0x20, 0xa0, 0xec, 0xed,
        0xef, 0xf1, 0xf3, 0xf4, 0xf5,
        0xf5, 0xf5, 0xf5, 0xf6, 0xf6,
        0xf6, 0xf7, 0xf8, 0xf7, 0xf8,
        0xf7, 0xf9, 0xf8, 0xf7, 0xf9,
        0xf8, 0xf8, 0xf6, 0xf8, 0xf8,
        0xf7, 0xf9, 0xf9, 0xf9, 0xf8,
        0xf7, 0xfa, 0xf8, 0xf8, 0xf7,
        0xfb, 0xfa, 0xf9, 0xf8, 0xf8
    ]

    test_result = [
        0, -1, -1, 0, 0,
        -1, 0, 0, -1, -1,
        0, 0, 0x1, 0x1, 0,
        -2, -1, -2, 0, -4,
        0x1, 0x1, 0x1, -5, 0x2,
        0x2, 0x3, 0xb, 0x14, 0x14,
        0x16, 0x18, 0x20, 0x21, 0x26,
        0x27, 0x2e, 0x2f, 0x33, 0x32,
        0x35, 0x33, 0x36, 0x34, 0x37,
        0x34, 0x37, 0x35, 0x38, 0x36,
        0x39, 0x38, 0x3b, 0x3a, 0x3f,
        0x3f, 0x40, 0x3a, 0x3d, 0x3e,
        0x41, 0x3c, 0x3e, 0x3f, 0x42,
        0x3e, 0x3b, 0x37, 0x3b, 0x3e,
        0x41, 0x3b, 0x3b, 0x3a, 0x3b,
        0x36, 0x39, 0x3b, 0x3f, 0x3c,
        0x3b, 0x37, 0x3b, 0x3d, 0x41,
        0x3d, 0x3e, 0x3c, 0x3e, 0x3b,
        0x3a, 0x37, 0x3b, 0x3e, 0x41,
        0x3c, 0x3b, 0x39, 0x3a, 0x36
    ]

    # Send input data
    for d in test_data:
        adpcm.data_in.wr(d)

    main_result = 0

    # Check compressed output (50 values)
    for i in range(IN_END // 2):
        d = adpcm.data_out.rd()
        print(d)
        main_result += (d != test_compressed[i])

    # Check result output (100 values)
    for i in range(IN_END):
        d = adpcm.data_out.rd()
        print(d)
        main_result += (d != test_result[i])

    assert 0 == main_result

