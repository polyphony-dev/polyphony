from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import List

MIN_WORD = -32768
MAX_WORD = 32767


@module
class GSM:
    def __init__(self):
        self.din = Handshake(int, "in")
        self.dout = Handshake(int, "out")
        self.larc_out = Handshake(int, "out")
        self.append_worker(self.gsm_main)

    def gsm_add(self, a, b):
        s = a + b
        if s < MIN_WORD:
            return MIN_WORD
        if s > MAX_WORD:
            return MAX_WORD
        return s

    def gsm_mult(self, a, b):
        if a == MIN_WORD:
            if b == MIN_WORD:
                return MAX_WORD
        return (a * b) >> 15

    def gsm_mult_r(self, a, b):
        if b == MIN_WORD:
            if a == MIN_WORD:
                return MAX_WORD
        return (a * b + 16384) >> 15

    def gsm_abs(self, a):
        if a < 0:
            if a == MIN_WORD:
                return MAX_WORD
            return -a
        return a

    def gsm_norm(self, a):
        bitoff = [
            8, 7, 6, 6, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4,
            3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
            2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
            2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ]
        if a < 0:
            if a <= -1073741824:
                return 0
            a = ~a
        if a & 0xffff0000:
            if a & 0xff000000:
                return -1 + bitoff[(a >> 24) & 0xFF]
            return 7 + bitoff[(a >> 16) & 0xFF]
        if a & 0xff00:
            return 15 + bitoff[(a >> 8) & 0xFF]
        return 23 + bitoff[a & 0xFF]

    def gsm_div(self, num, denum):
        if num == 0:
            return 0
        L_num = num
        L_denum = denum
        div = 0
        k = 15
        while k > 0:
            k = k - 1
            div = div << 1
            L_num = L_num << 1
            if L_num >= L_denum:
                L_num = L_num - L_denum
                div = div + 1
        return div

    def gsm_main(self):
        # Read 160 input samples
        s:List[int] = [0] * 160
        i = 0
        while i < 160:
            s[i] = self.din.rd()
            i = i + 1

        # === Autocorrelation ===
        # Find maximum
        smax = 0
        k = 0
        while k < 160:
            temp = self.gsm_abs(s[k])
            if temp > smax:
                smax = temp
            k = k + 1

        # Compute scaling factor
        scalauto = 0
        if smax != 0:
            scalauto = 4 - self.gsm_norm(smax << 16)

        # Scale signal
        if scalauto > 0:
            if scalauto <= 4:
                n = scalauto
                k = 0
                while k < 160:
                    s[k] = self.gsm_mult_r(s[k], 16384 >> (n - 1))
                    k = k + 1

        # Compute autocorrelation coefficients
        L_ACF:List[int] = [0] * 9
        i = 0
        while i < 160:
            sl = s[i]
            k = 0
            while k <= 8:
                if k <= i:
                    L_ACF[k] = L_ACF[k] + sl * s[i - k]
                k = k + 1
            i = i + 1

        k = 0
        while k < 9:
            L_ACF[k] = L_ACF[k] << 1
            k = k + 1

        # Rescale signal
        if scalauto > 0:
            k = 0
            while k < 160:
                s[k] = s[k] << scalauto
                k = k + 1

        # === Reflection coefficients ===
        r:List[int] = [0] * 8
        P:List[int] = [0] * 9
        K:List[int] = [0] * 9

        if L_ACF[0] != 0:
            temp_norm = self.gsm_norm(L_ACF[0])
            i = 0
            while i <= 8:
                P[i] = (L_ACF[i] << temp_norm) >> 16
                i = i + 1

            i = 1
            while i <= 7:
                K[i] = P[i]
                i = i + 1

            # Compute reflection coefficients with Schur recursion
            done = 0
            n = 1
            while n <= 8:
                do_schur = 0
                rn = 0
                if done == 0:
                    temp_abs = self.gsm_abs(P[1])
                    if P[0] >= temp_abs:
                        rn = self.gsm_div(temp_abs, P[0])
                        if P[1] > 0:
                            rn = -rn
                        r[n - 1] = rn
                        if n < 8:
                            do_schur = 1
                            temp2 = self.gsm_mult_r(P[1], rn)
                            P[0] = self.gsm_add(P[0], temp2)
                    else:
                        done = 1

                # Inner m-loop
                m = 1
                while m <= 8 - n:
                    if do_schur == 1:
                        temp2 = self.gsm_mult_r(K[m], rn)
                        new_P = self.gsm_add(P[m + 1], temp2)
                        temp2 = self.gsm_mult_r(P[m + 1], rn)
                        K[m] = self.gsm_add(K[m], temp2)
                        P[m] = new_P
                    m = m + 1
                n = n + 1

        # === Transformation to Log Area Ratios ===
        i = 0
        while i < 8:
            temp = r[i]
            temp = self.gsm_abs(temp)
            if temp < 22118:
                temp = temp >> 1
            elif temp < 31130:
                temp = temp - 11059
            else:
                temp = temp - 26112
                temp = temp << 2
            if r[i] < 0:
                r[i] = -temp
            else:
                r[i] = temp
            i = i + 1

        # === Quantization and coding ===
        LARc:List[int] = [0] * 8
        A_tbl = [20480, 20480, 20480, 20480, 13964, 15360, 8534, 9036]
        B_tbl = [0, 0, 2048, -2560, 94, -1792, -341, -1144]
        MAC_tbl = [31, 31, 15, 15, 7, 7, 3, 3]
        MIC_tbl = [-32, -32, -16, -16, -8, -8, -4, -4]

        i = 0
        while i < 8:
            temp = self.gsm_mult(A_tbl[i], r[i])
            temp = self.gsm_add(temp, B_tbl[i])
            temp = self.gsm_add(temp, 256)
            temp = temp >> 9
            if temp > MAC_tbl[i]:
                LARc[i] = MAC_tbl[i] - MIC_tbl[i]
            elif temp < MIC_tbl[i]:
                LARc[i] = 0
            else:
                LARc[i] = temp - MIC_tbl[i]
            i = i + 1

        # Output processed signal
        i = 0
        while i < 160:
            self.dout.wr(s[i])
            i = i + 1

        # Output LARc coefficients
        i = 0
        while i < 8:
            self.larc_out.wr(LARc[i])
            i = i + 1


@testbench
def test():
    gsm = GSM()

    inData:List[int] = [
        81, 10854, 1893, -10291, 7614, 29718, 20475, -29215, -18949, -29806,
        -32017, 1596, 15744, -3088, -17413, -22123, 6798, -13276, 3819, -16273,
        -1573, -12523, -27103,
        -193, -25588, 4698, -30436, 15264, -1393, 11418, 11370, 4986, 7869, -1903,
        9123, -31726,
        -25237, -14155, 17982, 32427, -12439, -15931, -21622, 7896, 1689, 28113,
        3615, 22131, -5572,
        -20110, 12387, 9177, -24544, 12480, 21546, -17842, -13645, 20277, 9987,
        17652, -11464, -17326,
        -10552, -27100, 207, 27612, 2517, 7167, -29734, -22441, 30039, -2368, 12813,
        300, -25555, 9087,
        29022, -6559, -20311, -14347, -7555, -21709, -3676, -30082, -3190, -30979,
        8580, 27126, 3414,
        -4603, -22303, -17143, 13788, -1096, -14617, 22071, -13552, 32646, 16689,
        -8473, -12733, 10503,
        20745, 6696, -26842, -31015, 3792, -19864, -20431, -30307, 32421, -13237,
        9006, 18249, 2403,
        -7996, -14827, -5860, 7122, 29817, -31894, 17955, 28836, -31297, 31821,
        -27502, 12276, -5587,
        -22105, 9192, -22549, 15675, -12265, 7212, -23749, -12856, -5857, 7521,
        17349, 13773, -3091,
        -17812, -9655, 26667, 7902, 2487, 3177, 29412, -20224, -2776, 24084, -7963,
        -10438, -11938,
        -14833, -6658, 32058, 4020, 10461, 15159,
    ]

    outData:List[int] = [
        80, 10848, 1888, -10288, 7616, 29712, 20480, -29216, -18944, -29808,
        -32016, 1600, 15744, -3088, -17408, -22128, 6800, -13280, 3824, -16272,
        -1568, -12528, -27104,
        -192, -25584, 4704, -30432, 15264, -1392, 11424, 11376, 4992, 7872, -1904,
        9120, -31728, -25232,
        -14160, 17984, 32432, -12432, -15936, -21616, 7904, 1696, 28112, 3616,
        22128, -5568, -20112,
        12384, 9184, -24544, 12480, 21552, -17840, -13648, 20272, 9984, 17648,
        -11456, -17328, -10544,
        -27104, 208, 27616, 2512, 7168, -29728, -22448, 30032, -2368, 12816, 304,
        -25552, 9088, 29024,
        -6560, -20304, -14352, -7552, -21712, -3680, -30080, -3184, -30976, 8576,
        27120, 3408, -4608,
        -22304, -17136, 13792, -1088, -14624, 22064, -13552, 32640, 16688, -8480,
        -12736, 10496, 20752,
        6704, -26848, -31008, 3792, -19856, -20432, -30304, 32416, -13232, 9008,
        18256, 2400, -8000,
        -14832, -5856, 7120, 29824, -31888, 17952, 28832, -31296, 31824, -27504,
        12272, -5584, -22112,
        9200, -22544, 15680, -12272, 7216, -23744, -12848, -5856, 7520, 17344,
        13776, -3088, -17808,
        -9648, 26672, 7904, 2480, 3184, 29408, -20224, -2768, 24080, -7968, -10432,
        -11936, -14832,
        -6656, 32064, 4016, 10464, 15152,
    ]

    outLARc:List[int] = [32, 33, 22, 13, 7, 5, 3, 2]

    # Feed input samples
    for i in range(160):
        gsm.din.wr(inData[i])

    # Verify processed signal output
    main_result = 0
    for i in range(160):
        result = gsm.dout.rd()
        main_result += (result != outData[i])

    # Verify LARc coefficients
    for i in range(8):
        result = gsm.larc_out.rd()
        main_result += (result != outLARc[i])

    assert 0 == main_result
