from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake


MV_FIELD = 0


@module
class Motion:
    def __init__(self):
        self.din = Handshake(int, "in")
        self.dout = Handshake(int, "out")
        self.append_worker(self.motion_main)

    def Show_Bits(self, ld_Bfr:int, N:int) -> int:
        # Logical right shift: mask to N bits to avoid sign extension
        return (ld_Bfr >> (32 - N)) & ((1 << N) - 1)

    def Flush_Buffer(self, ld_Bfr:int, ld_Incnt:int, ld_Rdptr_idx:int,
                     ld_Rdbfr:list, N:int) -> tuple:
        ld_Bfr = (ld_Bfr << N) & 0xFFFFFFFF
        Incnt = ld_Incnt - N

        if Incnt <= 24:
            if ld_Rdptr_idx < 2044:
                while Incnt <= 24:
                    ld_Bfr = (ld_Bfr | (ld_Rdbfr[ld_Rdptr_idx] << (24 - Incnt))) & 0xFFFFFFFF
                    ld_Rdptr_idx = ld_Rdptr_idx + 1
                    Incnt = Incnt + 8
            else:
                while Incnt <= 24:
                    if ld_Rdptr_idx >= 2048:
                        ld_Rdptr_idx = 0
                    ld_Bfr = (ld_Bfr | (ld_Rdbfr[ld_Rdptr_idx] << (24 - Incnt))) & 0xFFFFFFFF
                    ld_Rdptr_idx = ld_Rdptr_idx + 1
                    Incnt = Incnt + 8

        return (ld_Bfr, Incnt, ld_Rdptr_idx)

    def Get_Bits(self, ld_Bfr:int, ld_Incnt:int, ld_Rdptr_idx:int,
                 ld_Rdbfr:list, N:int) -> tuple:
        Val = self.Show_Bits(ld_Bfr, N)
        result = self.Flush_Buffer(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, N)
        ld_Bfr = result[0]
        ld_Incnt = result[1]
        ld_Rdptr_idx = result[2]
        return (Val, ld_Bfr, ld_Incnt, ld_Rdptr_idx)

    def skip_bits(self, ld_Bfr:int, ld_Incnt:int, ld_Rdptr_idx:int,
                  ld_Rdbfr:list, N:int) -> tuple:
        while N > 0:
            chunk = N
            if chunk > 24:
                chunk = 24
            result = self.Flush_Buffer(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, chunk)
            ld_Bfr = result[0]
            ld_Incnt = result[1]
            ld_Rdptr_idx = result[2]
            N = N - chunk
        return (ld_Bfr, ld_Incnt, ld_Rdptr_idx)

    def Get_Bits_large(self, ld_Bfr:int, ld_Incnt:int, ld_Rdptr_idx:int,
                       ld_Rdbfr:list, N:int) -> tuple:
        # For N >= 32, the effective bit count is N % 32
        eff_N = N & 31
        Val = self.Show_Bits(ld_Bfr, eff_N)
        result = self.Flush_Buffer(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, eff_N)
        ld_Bfr = result[0]
        ld_Incnt = result[1]
        ld_Rdptr_idx = result[2]
        # Skip the remaining bits
        remain = N - eff_N
        result = self.skip_bits(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, remain)
        ld_Bfr = result[0]
        ld_Incnt = result[1]
        ld_Rdptr_idx = result[2]
        return (Val, ld_Bfr, ld_Incnt, ld_Rdptr_idx)

    def Get_motion_code(self, ld_Bfr:int, ld_Incnt:int, ld_Rdptr_idx:int,
                        ld_Rdbfr:list, tab0_val:list, tab0_len:list,
                        tab1_val:list, tab1_len:list,
                        tab2_val:list, tab2_len:list) -> tuple:
        r = self.Get_Bits(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, 1)
        bit1 = r[0]
        ld_Bfr = r[1]
        ld_Incnt = r[2]
        ld_Rdptr_idx = r[3]

        if bit1:
            return (0, ld_Bfr, ld_Incnt, ld_Rdptr_idx)

        code = self.Show_Bits(ld_Bfr, 9)

        if code >= 64:
            code = code >> 6
            r2 = self.Flush_Buffer(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, tab0_len[code])
            ld_Bfr = r2[0]
            ld_Incnt = r2[1]
            ld_Rdptr_idx = r2[2]
            r3 = self.Get_Bits(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, 1)
            sign_bit = r3[0]
            ld_Bfr = r3[1]
            ld_Incnt = r3[2]
            ld_Rdptr_idx = r3[3]
            if sign_bit:
                return (-tab0_val[code], ld_Bfr, ld_Incnt, ld_Rdptr_idx)
            else:
                return (tab0_val[code], ld_Bfr, ld_Incnt, ld_Rdptr_idx)

        if code >= 24:
            code = code >> 3
            r2 = self.Flush_Buffer(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, tab1_len[code])
            ld_Bfr = r2[0]
            ld_Incnt = r2[1]
            ld_Rdptr_idx = r2[2]
            r3 = self.Get_Bits(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, 1)
            sign_bit = r3[0]
            ld_Bfr = r3[1]
            ld_Incnt = r3[2]
            ld_Rdptr_idx = r3[3]
            if sign_bit:
                return (-tab1_val[code], ld_Bfr, ld_Incnt, ld_Rdptr_idx)
            else:
                return (tab1_val[code], ld_Bfr, ld_Incnt, ld_Rdptr_idx)

        code = code - 12
        if code < 0:
            return (0, ld_Bfr, ld_Incnt, ld_Rdptr_idx)

        r2 = self.Flush_Buffer(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, tab2_len[code])
        ld_Bfr = r2[0]
        ld_Incnt = r2[1]
        ld_Rdptr_idx = r2[2]
        r3 = self.Get_Bits(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, 1)
        sign_bit = r3[0]
        ld_Bfr = r3[1]
        ld_Incnt = r3[2]
        ld_Rdptr_idx = r3[3]
        if sign_bit:
            return (-tab2_val[code], ld_Bfr, ld_Incnt, ld_Rdptr_idx)
        else:
            return (tab2_val[code], ld_Bfr, ld_Incnt, ld_Rdptr_idx)

    def decode_motion_vector(self, pred:int, r_size:int, motion_code:int,
                             motion_residual:int, full_pel_vector:int) -> int:
        r_size = r_size % 32
        lim = 16 << r_size
        if full_pel_vector:
            vec = pred >> 1
        else:
            vec = pred

        if motion_code > 0:
            vec = vec + ((motion_code - 1) << r_size) + motion_residual + 1
            if vec >= lim:
                vec = vec - lim - lim
        elif motion_code < 0:
            vec = vec - ((-motion_code - 1) << r_size) - motion_residual - 1
            if vec < -lim:
                vec = vec + lim + lim

        if full_pel_vector:
            pred = vec << 1
        else:
            pred = vec
        return pred

    def motion_main(self):
        # VLC lookup tables (local)
        tab0_val = [-1, 3, 2, 2, 1, 1, 1, 1]
        tab0_len = [0, 3, 2, 2, 1, 1, 1, 1]
        tab1_val = [-1, -1, -1, 7, 6, 5, 4, 4]
        tab1_len = [0, 0, 0, 6, 6, 6, 5, 5]
        tab2_val = [16, 15, 14, 13, 12, 11, 10, 10, 9, 9, 8, 8]
        tab2_len = [9, 9, 9, 9, 9, 9, 8, 8, 8, 8, 8, 8]

        # Read inRdbfr (2048 bytes)
        ld_Rdbfr = [0] * 2048
        for i in range(2048):
            ld_Rdbfr[i] = self.din.rd()

        # Read inPMV[2][2][2] - flattened to 8 values
        inPMV = [0] * 8
        for i in range(8):
            inPMV[i] = self.din.rd()

        # Read inmvfs[2][2] - flattened to 4 values
        inmvfs = [0] * 4
        for i in range(4):
            inmvfs[i] = self.din.rd()

        # Initialize buffer state
        ld_Incnt = 0
        ld_Bfr = 68157440  # 0x04100000

        # Initialize PMV and mvfs
        PMV = [0] * 8
        for i in range(8):
            PMV[i] = inPMV[i]

        mvfs = [0] * 4
        for i in range(4):
            mvfs[i] = inmvfs[i]

        # Parameters
        s = 0
        mv_format = 0
        h_r_size = 200
        v_r_size = 200
        dmv = 0
        mvscale = 1

        # Initialize_Buffer: Fill_Buffer + Flush_Buffer(0)
        ld_Rdptr_idx = 0
        r = self.Flush_Buffer(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, 0)
        ld_Bfr = r[0]
        ld_Incnt = r[1]
        ld_Rdptr_idx = r[2]

        # motion_vectors (motion_vector_count == 1)
        if mv_format == MV_FIELD and dmv == 0:
            r = self.Get_Bits(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, 1)
            field_sel = r[0]
            ld_Bfr = r[1]
            ld_Incnt = r[2]
            ld_Rdptr_idx = r[3]
            mvfs[1 * 2 + s] = field_sel
            mvfs[0 * 2 + s] = field_sel

        # motion_vector for PMV[0][s]: horizontal component
        r = self.Get_motion_code(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr,
                                 tab0_val, tab0_len, tab1_val, tab1_len,
                                 tab2_val, tab2_len)
        motion_code = r[0]
        ld_Bfr = r[1]
        ld_Incnt = r[2]
        ld_Rdptr_idx = r[3]

        if h_r_size != 0 and motion_code != 0:
            r = self.Get_Bits_large(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, h_r_size)
            motion_residual = r[0]
            ld_Bfr = r[1]
            ld_Incnt = r[2]
            ld_Rdptr_idx = r[3]
        else:
            motion_residual = 0

        PMV[0] = self.decode_motion_vector(
            PMV[0], h_r_size, motion_code, motion_residual, 0)

        # vertical component
        r = self.Get_motion_code(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr,
                                 tab0_val, tab0_len, tab1_val, tab1_len,
                                 tab2_val, tab2_len)
        motion_code = r[0]
        ld_Bfr = r[1]
        ld_Incnt = r[2]
        ld_Rdptr_idx = r[3]

        if v_r_size != 0 and motion_code != 0:
            r = self.Get_Bits_large(ld_Bfr, ld_Incnt, ld_Rdptr_idx, ld_Rdbfr, v_r_size)
            motion_residual = r[0]
            ld_Bfr = r[1]
            ld_Incnt = r[2]
            ld_Rdptr_idx = r[3]
        else:
            motion_residual = 0

        if mvscale != 0:
            PMV[1] = PMV[1] >> 1
        # Inline decode_motion_vector for vertical (motion_code=0 means no change)
        if motion_code > 0:
            r_eff = v_r_size % 32
            lim = 16 << r_eff
            vec = PMV[1] + ((motion_code - 1) << r_eff) + motion_residual + 1
            if vec >= lim:
                vec = vec - lim - lim
            PMV[1] = vec
        elif motion_code < 0:
            r_eff = v_r_size % 32
            lim = 16 << r_eff
            vec = PMV[1] - ((-motion_code - 1) << r_eff) - motion_residual - 1
            if vec < -lim:
                vec = vec + lim + lim
            PMV[1] = vec
        if mvscale != 0:
            PMV[1] = PMV[1] << 1

        # Update other motion vector predictors
        PMV[1 * 4 + s * 2 + 0] = PMV[0 * 4 + s * 2 + 0]
        PMV[1 * 4 + s * 2 + 1] = PMV[0 * 4 + s * 2 + 1]

        # Output PMV[2][2][2] (8 values)
        for i in range(8):
            self.dout.wr(PMV[i])

        # Output mvfs[2][2] (4 values)
        for i in range(4):
            self.dout.wr(mvfs[i])


@testbench
def test():
    m = Motion()

    # inRdbfr (2048 bytes)
    inRdbfr = [
        0, 104, 120, 48, 72, 32, 160, 192, 192, 64, 56, 248, 248, 88, 136, 224, 200,
        208, 176, 72, 96, 40, 184, 160, 32, 32, 120, 168, 64, 32, 72, 184,
        216, 240, 0, 216, 192, 64, 112, 48, 160, 152, 40, 176, 32, 32, 248, 200,
        104, 24, 216, 240, 128, 176, 72, 232, 240, 184, 48, 120, 48, 192, 64, 168,
        160, 128, 160, 160, 232, 208, 104, 120, 232, 120, 8, 184, 120, 200, 64, 160,
        200, 224, 64, 168, 40, 120, 80, 104, 16, 0, 8, 120, 144, 136, 80, 144,
        72, 24, 128, 216, 216, 24, 80, 16, 64, 32, 200, 112, 128, 144, 88, 24, 112,
        120, 32, 104, 72, 176, 24, 16, 184, 56, 24, 200, 152, 152, 48, 48,
        136, 80, 240, 8, 216, 200, 240, 32, 168, 112, 48, 56, 40, 192, 232, 32, 48,
        232, 232, 32, 0, 88, 208, 24, 240, 72, 120, 96, 248, 136, 224, 208,
        8, 184, 192, 144, 88, 48, 144, 136, 112, 192, 96, 240, 200, 160, 184, 160,
        24, 48, 208, 152, 128, 184, 184, 144, 144, 168, 240, 144, 160, 168, 48,
        48,
        24, 200, 144, 120, 208, 56, 96, 72, 48, 88, 80, 200, 248, 208, 248, 40, 136,
        112, 32, 8, 8, 80, 192, 40, 32, 224, 56, 192, 200, 56, 56, 232,
        200, 80, 120, 8, 184, 216, 232, 80, 168, 128, 32, 216, 136, 104, 248, 168,
        248, 8, 192, 168, 192, 56, 240, 192, 208, 136, 120, 48, 224, 112, 168, 80,
        192, 96, 80, 120, 120, 16, 120, 48, 168, 168, 160, 224, 128, 24, 72, 24,
        248, 240, 152, 160, 208, 56, 192, 56, 88, 128, 192, 136, 128, 208, 112,
        40,
        64, 192, 32, 176, 80, 56, 168, 208, 24, 168, 168, 248, 240, 136, 96, 32, 56,
        184, 8, 136, 16, 0, 176, 40, 0, 32, 104, 160, 56, 88, 232, 56,
        0, 240, 184, 232, 88, 32, 176, 0, 216, 248, 184, 40, 16, 80, 8, 208, 64,
        224, 72, 40, 72, 72, 144, 80, 144, 120, 136, 64, 184, 160, 136, 16,
        48, 104, 232, 104, 104, 72, 208, 72, 192, 184, 40, 56, 232, 72, 160, 80,
        152, 232, 248, 32, 224, 40, 0, 168, 24, 96, 112, 160, 152, 8, 32, 160,
        104, 208, 32, 24, 248, 8, 248, 144, 120, 16, 192, 88, 152, 176, 200, 160,
        152, 160, 96, 168, 240, 16, 248, 176, 24, 216, 0, 56, 80, 248, 96, 8,
        128, 32, 192, 104, 48, 208, 240, 184, 128, 80, 56, 192, 0, 112, 176, 48, 96,
        56, 24, 56, 24, 32, 24, 96, 80, 0, 64, 112, 48, 24, 88, 56,
        152, 224, 160, 192, 184, 72, 248, 128, 8, 8, 104, 104, 200, 48, 136, 136,
        208, 144, 80, 40, 136, 96, 8, 208, 160, 104, 160, 80, 64, 96, 176, 144,
        8, 56, 88, 88, 208, 120, 48, 240, 240, 96, 248, 192, 104, 128, 248, 24, 104,
        72, 64, 120, 248, 192, 48, 192, 32, 80, 144, 16, 80, 96, 112, 184,
        56, 80, 248, 232, 0, 40, 248, 56, 192, 32, 192, 96, 248, 48, 136, 224, 80,
        0, 192, 128, 104, 120, 208, 128, 0, 176, 216, 8, 192, 96, 16, 40,
        184, 96, 32, 72, 80, 192, 104, 104, 136, 0, 16, 160, 24, 104, 48, 8, 24,
        152, 120, 128, 72, 32, 176, 112, 104, 120, 16, 32, 144, 160, 56, 240,
        0, 232, 184, 24, 16, 208, 200, 240, 200, 200, 104, 112, 24, 208, 128, 168,
        248, 64, 152, 120, 64, 224, 128, 208, 120, 216, 16, 152, 48, 144, 240, 80,
        144, 224, 48, 160, 192, 248, 0, 128, 120, 128, 160, 232, 168, 208, 112, 112,
        104, 184, 8, 192, 56, 176, 40, 96, 64, 72, 104, 216, 152, 216, 80, 152,
        184, 216, 32, 56, 32, 64, 240, 152, 240, 168, 136, 8, 232, 168, 128, 88, 72,
        128, 8, 192, 48, 120, 112, 32, 144, 208, 192, 216, 16, 176, 168, 160,
        168, 88, 136, 56, 8, 64, 0, 80, 216, 104, 64, 80, 88, 208, 64, 80, 200, 24,
        120, 160, 80, 72, 56, 216, 24, 56, 72, 40, 72, 0, 56, 136,
        56, 200, 72, 136, 88, 72, 136, 240, 0, 176, 176, 152, 192, 248, 224, 240,
        72, 8, 112, 232, 200, 120, 16, 0, 40, 48, 64, 72, 32, 136, 104, 152,
        16, 240, 184, 80, 0, 152, 32, 176, 128, 120, 0, 160, 40, 64, 112, 40, 80,
        48, 144, 96, 168, 0, 152, 72, 184, 136, 88, 152, 184, 48, 88, 152,
        96, 216, 240, 184, 200, 136, 64, 104, 112, 232, 0, 208, 176, 128, 112, 248,
        144, 248, 120, 112, 0, 120, 240, 88, 88, 88, 8, 248, 80, 8, 64, 216,
        240, 56, 56, 144, 112, 208, 144, 72, 16, 160, 136, 216, 176, 112, 56, 8,
        168, 104, 72, 40, 176, 88, 40, 120, 24, 40, 56, 104, 40, 160, 232, 160,
        24, 144, 144, 232, 120, 144, 112, 96, 136, 176, 8, 128, 112, 184, 96, 120,
        64, 112, 0, 184, 80, 72, 184, 80, 144, 72, 120, 200, 168, 32, 24, 0,
        144, 72, 24, 248, 24, 152, 72, 128, 0, 8, 224, 32, 72, 72, 48, 112, 232, 16,
        240, 24, 64, 32, 232, 120, 168, 200, 152, 112, 8, 144, 0, 120,
        112, 0, 112, 144, 72, 160, 24, 216, 112, 128, 224, 152, 104, 136, 40, 0, 16,
        144, 48, 248, 136, 48, 64, 88, 152, 208, 248, 16, 112, 224, 184, 168,
        40, 168, 64, 248, 144, 104, 200, 144, 152, 16, 168, 192, 240, 96, 72, 136,
        216, 136, 0, 32, 192, 112, 240, 160, 248, 184, 16, 48, 232, 88, 160, 16,
        104, 176, 144, 136, 24, 240, 184, 160, 8, 16, 32, 56, 176, 144, 168, 168,
        56, 88, 88, 104, 248, 184, 96, 32, 128, 88, 224, 240, 32, 120, 216, 136,
        8, 72, 80, 104, 120, 152, 32, 96, 232, 80, 232, 24, 80, 200, 208, 216, 184,
        16, 56, 40, 216, 208, 128, 120, 16, 16, 80, 200, 144, 104, 160, 72,
        24, 136, 176, 32, 192, 120, 136, 80, 16, 88, 208, 160, 16, 232, 40, 24, 144,
        208, 32, 16, 88, 192, 48, 176, 152, 24, 160, 32, 80, 24, 240, 80,
        160, 152, 160, 128, 80, 88, 40, 184, 208, 144, 48, 200, 200, 48, 112, 144,
        104, 224, 144, 224, 200, 8, 224, 240, 32, 152, 232, 16, 8, 50, 184, 40,
        184, 248, 64, 8, 232, 16, 88, 88, 8, 120, 128, 48, 240, 88, 64, 104, 104,
        248, 96, 240, 192, 152, 208, 56, 152, 240, 136, 8, 216, 24, 112, 168,
        88, 136, 80, 224, 136, 152, 40, 24, 248, 216, 152, 136, 96, 224, 64, 80, 56,
        56, 72, 8, 24, 64, 144, 24, 208, 216, 128, 120, 96, 168, 120, 152,
        112, 232, 136, 80, 72, 96, 152, 208, 72, 216, 64, 120, 120, 48, 232, 72,
        184, 176, 48, 232, 200, 184, 120, 72, 112, 128, 248, 160, 168, 216, 152,
        80,
        176, 112, 48, 152, 112, 64, 40, 200, 232, 80, 160, 56, 216, 192, 168, 72,
        40, 64, 208, 32, 224, 240, 24, 104, 232, 240, 168, 24, 248, 32, 80, 152,
        144, 160, 112, 120, 96, 240, 64, 160, 248, 248, 152, 48, 112, 88, 128, 232,
        240, 240, 232, 168, 120, 32, 152, 176, 104, 16, 80, 152, 240, 224, 128,
        16,
        48, 32, 216, 8, 104, 248, 184, 208, 216, 120, 80, 208, 128, 56, 112, 40,
        184, 16, 224, 168, 152, 248, 56, 144, 168, 224, 8, 168, 80, 136, 152, 48,
        96, 0, 184, 88, 192, 24, 16, 128, 0, 176, 152, 40, 96, 72, 192, 0, 32, 128,
        24, 240, 48, 248, 176, 120, 16, 168, 224, 72, 8, 200, 48, 176,
        112, 224, 160, 8, 152, 64, 16, 16, 240, 224, 64, 144, 128, 80, 184, 40, 232,
        200, 112, 248, 24, 112, 176, 128, 128, 56, 40, 152, 24, 184, 120, 104,
        72, 64, 200, 48, 224, 0, 56, 232, 32, 240, 184, 104, 104, 32, 192, 200, 200,
        64, 152, 72, 216, 216, 80, 0, 80, 0, 0, 160, 120, 40, 136, 240,
        32, 120, 152, 216, 56, 112, 16, 24, 8, 120, 104, 192, 144, 176, 8, 16, 96,
        104, 168, 80, 192, 232, 112, 112, 56, 88, 176, 240, 32, 176, 248, 80,
        176, 24, 224, 192, 8, 176, 168, 16, 232, 248, 16, 16, 104, 128, 232, 0, 32,
        240, 112, 32, 184, 184, 56, 232, 80, 144, 16, 72, 240, 208, 64, 176,
        240, 16, 136, 16, 80, 192, 24, 72, 216, 56, 80, 216, 32, 144, 72, 24, 64,
        248, 0, 224, 72, 32, 136, 232, 240, 72, 32, 88, 128, 104, 16, 8,
        32, 192, 224, 8, 152, 248, 224, 0, 176, 48, 16, 104, 216, 176, 24, 240, 200,
        80, 248, 208, 128, 200, 72, 8, 152, 128, 80, 120, 80, 152, 232, 200,
        168, 88, 16, 176, 232, 40, 72, 208, 232, 112, 240, 112, 80, 176, 176, 16,
        72, 120, 32, 184, 224, 80, 24, 176, 0, 208, 16, 56, 112, 16, 120, 160,
        24, 216, 128, 136, 192, 152, 248, 120, 160, 56, 192, 224, 0, 136, 112, 112,
        8, 8, 184, 168, 88, 160, 120, 160, 240, 168, 32, 40, 168, 88, 8, 16,
        24, 104, 104, 48, 248, 136, 72, 144, 128, 160, 216, 88, 240, 120, 232, 72,
        192, 200, 248, 192, 48, 240, 104, 208, 40, 104, 16, 128, 80, 224, 224, 56,
        56, 120, 40, 24, 176, 16, 184, 24, 176, 224, 168, 16, 184, 104, 136, 200,
        168, 208, 120, 200, 224, 40, 208, 16, 112, 160, 192, 224, 64, 40, 232,
        120,
        24, 232, 168, 80, 88, 144, 104, 72, 192, 112, 0, 112, 104, 224, 232, 160,
        112, 208, 176, 216, 56, 224, 224, 160, 104, 56, 176, 216, 192, 24, 208, 8,
        40, 56, 248, 8, 120, 184, 128, 40, 168, 56, 184, 192, 136, 96, 72, 216, 8,
        64, 72, 56, 16, 176, 144, 16, 128, 176, 136, 208, 120, 16, 184, 224,
        160, 216, 144, 88, 208, 200, 144, 96, 152, 200, 224, 208, 240, 120, 8, 104,
        184, 112, 168, 200, 112, 72, 0, 192, 0, 40, 120, 136, 112, 40, 152, 56,
        144, 32, 224, 240, 32, 192, 56, 200, 16, 136, 104, 192, 192, 0, 0, 0, 8,
        232, 104, 240, 88, 192, 8, 168, 216, 208, 184, 224, 240, 72, 152, 72,
        168, 184, 176, 216, 48, 144, 80, 32, 184, 208, 112, 160, 88, 88, 8, 144,
        144, 120, 152, 48, 200, 168, 112, 8, 160, 216, 240, 128, 104, 128, 144,
        248,
        64, 168, 136, 240, 160, 56, 136, 216, 80, 56, 192, 32, 64, 128, 80, 32, 32,
        96, 88, 200, 152, 72, 160, 16, 128, 200, 160, 144, 112, 16, 112, 152,
        56, 136, 56, 216, 8, 24, 192, 144, 176, 200, 48, 72, 40, 72, 240, 120, 120,
        160, 80, 152, 144, 216, 224, 152, 40, 144, 160, 88, 184, 184, 192, 128,
        0, 200, 72, 112, 208, 248, 152, 0, 152, 8, 40, 16, 168, 152, 64, 176, 88,
        24, 232, 136, 32, 152, 232, 208, 192, 240, 136, 0, 232, 200, 8, 216,
        104, 184, 64, 192, 8, 96, 184, 120, 208, 80, 16, 64, 136, 136, 72, 8, 112,
        184, 248, 120, 136, 8, 56, 232, 208, 96, 16, 64, 168, 112, 48, 32,
        184, 224, 72, 88, 128, 184, 72, 168, 224, 216, 160, 232, 64, 168, 48, 152,
        64, 152, 16, 200, 168, 56, 144, 192, 64, 120, 168, 8, 128, 216, 16, 8,
        104, 32, 128, 96, 160, 88, 136, 96, 56, 16, 128, 56, 88, 16, 208, 200, 24,
        96, 240, 32, 232, 192, 104, 168, 40, 0, 192, 40, 200, 96, 184, 8,
        72, 216, 104, 232, 112, 248, 8, 8, 248, 192, 152, 32, 0, 168, 232, 80, 248,
        64, 8, 24, 80, 32, 96, 240, 232, 48, 80, 16, 144, 200, 16, 48,
        88, 40, 112, 232, 88, 168, 56, 160, 232, 16, 128, 248, 48, 80, 200, 168,
        152, 72, 216, 224, 72, 208, 152, 192, 0, 224, 48, 136, 168, 96, 16, 152
    ]

    for d in inRdbfr:
        m.din.wr(d)

    # inPMV[2][2][2] flattened
    inPMV = [45, 207, 70, 41, 4, 180, 120, 216]
    for d in inPMV:
        m.din.wr(d)

    # inmvfs[2][2] flattened
    inmvfs = [232, 200, 32, 240]
    for d in inmvfs:
        m.din.wr(d)

    # Expected output
    outPMV = [1566, 206, 70, 41, 1566, 206, 120, 216]
    outmvfs = [0, 200, 0, 240]

    main_result = 0
    for i in range(8):
        d = m.dout.rd()
        print(d)
        main_result += (d != outPMV[i])
    for i in range(4):
        d = m.dout.rd()
        print(d)
        main_result += (d != outmvfs[i])

    assert 0 == main_result
