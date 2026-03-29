from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake


@module
class AES:
    def __init__(self):
        self.statemt_in = Handshake(int, "in")
        self.key_in = Handshake(int, "in")
        self.statemt_out = Handshake(int, "out")
        self.append_worker(self.aes_main)

    def aes_main(self):
        # S-box (Sbox[16][16] flattened to 256)
        sbox = [
            0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5,
            0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
            0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0,
            0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
            0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc,
            0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
            0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a,
            0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
            0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0,
            0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
            0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b,
            0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
            0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85,
            0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
            0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5,
            0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
            0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17,
            0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
            0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88,
            0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
            0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c,
            0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
            0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9,
            0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
            0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6,
            0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
            0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e,
            0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
            0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94,
            0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
            0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68,
            0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
        ]
        # Inverse S-box (invSbox[16][16] flattened to 256)
        invsbox = [
            0x52, 0x09, 0x6a, 0xd5, 0x30, 0x36, 0xa5, 0x38,
            0xbf, 0x40, 0xa3, 0x9e, 0x81, 0xf3, 0xd7, 0xfb,
            0x7c, 0xe3, 0x39, 0x82, 0x9b, 0x2f, 0xff, 0x87,
            0x34, 0x8e, 0x43, 0x44, 0xc4, 0xde, 0xe9, 0xcb,
            0x54, 0x7b, 0x94, 0x32, 0xa6, 0xc2, 0x23, 0x3d,
            0xee, 0x4c, 0x95, 0x0b, 0x42, 0xfa, 0xc3, 0x4e,
            0x08, 0x2e, 0xa1, 0x66, 0x28, 0xd9, 0x24, 0xb2,
            0x76, 0x5b, 0xa2, 0x49, 0x6d, 0x8b, 0xd1, 0x25,
            0x72, 0xf8, 0xf6, 0x64, 0x86, 0x68, 0x98, 0x16,
            0xd4, 0xa4, 0x5c, 0xcc, 0x5d, 0x65, 0xb6, 0x92,
            0x6c, 0x70, 0x48, 0x50, 0xfd, 0xed, 0xb9, 0xda,
            0x5e, 0x15, 0x46, 0x57, 0xa7, 0x8d, 0x9d, 0x84,
            0x90, 0xd8, 0xab, 0x00, 0x8c, 0xbc, 0xd3, 0x0a,
            0xf7, 0xe4, 0x58, 0x05, 0xb8, 0xb3, 0x45, 0x06,
            0xd0, 0x2c, 0x1e, 0x8f, 0xca, 0x3f, 0x0f, 0x02,
            0xc1, 0xaf, 0xbd, 0x03, 0x01, 0x13, 0x8a, 0x6b,
            0x3a, 0x91, 0x11, 0x41, 0x4f, 0x67, 0xdc, 0xea,
            0x97, 0xf2, 0xcf, 0xce, 0xf0, 0xb4, 0xe6, 0x73,
            0x96, 0xac, 0x74, 0x22, 0xe7, 0xad, 0x35, 0x85,
            0xe2, 0xf9, 0x37, 0xe8, 0x1c, 0x75, 0xdf, 0x6e,
            0x47, 0xf1, 0x1a, 0x71, 0x1d, 0x29, 0xc5, 0x89,
            0x6f, 0xb7, 0x62, 0x0e, 0xaa, 0x18, 0xbe, 0x1b,
            0xfc, 0x56, 0x3e, 0x4b, 0xc6, 0xd2, 0x79, 0x20,
            0x9a, 0xdb, 0xc0, 0xfe, 0x78, 0xcd, 0x5a, 0xf4,
            0x1f, 0xdd, 0xa8, 0x33, 0x88, 0x07, 0xc7, 0x31,
            0xb1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xec, 0x5f,
            0x60, 0x51, 0x7f, 0xa9, 0x19, 0xb5, 0x4a, 0x0d,
            0x2d, 0xe5, 0x7a, 0x9f, 0x93, 0xc9, 0x9c, 0xef,
            0xa0, 0xe0, 0x3b, 0x4d, 0xae, 0x2a, 0xf5, 0xb0,
            0xc8, 0xeb, 0xbb, 0x3c, 0x83, 0x53, 0x99, 0x61,
            0x17, 0x2b, 0x04, 0x7e, 0xba, 0x77, 0xd6, 0x26,
            0xe1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0c, 0x7d,
        ]
        rcon = [
            0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80,
            0x1b, 0x36, 0x6c, 0xd8, 0xab, 0x4d, 0x9a, 0x2f,
            0x5e, 0xbc, 0x63, 0xc6, 0x97, 0x35, 0x6a, 0xd4,
            0xb3, 0x7d, 0xfa, 0xef, 0xc5, 0x91,
        ]
        # Working arrays (all local)
        word0 = [0] * 44  # nb * (round_val + 1) = 4 * 11 = 44
        word1 = [0] * 44
        word2 = [0] * 44
        word3 = [0] * 44
        st = [0] * 32
        key = [0] * 32
        ret = [0] * 32

        # Read plaintext (16 bytes)
        i = 0
        while i < 16:
            st[i] = self.statemt_in.rd()
            i = i + 1
        # Read key (16 bytes)
        i = 0
        while i < 16:
            key[i] = self.key_in.rd()
            i = i + 1

        # ============================================================
        # ENCRYPT (type=128128, nk=4, nb=4, enc_round_val=0)
        # ============================================================

        # --- KeySchedule (nk=4, nb=4, round_val=10) ---
        j = 0
        while j < 4:
            word0[j] = key[0 + j * 4]
            word1[j] = key[1 + j * 4]
            word2[j] = key[2 + j * 4]
            word3[j] = key[3 + j * 4]
            j = j + 1
        j = 4
        while j < 44:
            temp0 = 0; temp1 = 0; temp2 = 0; temp3 = 0
            if (j % 4) == 0:
                temp0 = sbox[word1[j - 1]] ^ rcon[(j // 4) - 1]
                temp1 = sbox[word2[j - 1]]
                temp2 = sbox[word3[j - 1]]
                temp3 = sbox[word0[j - 1]]
            else:
                temp0 = word0[j - 1]
                temp1 = word1[j - 1]
                temp2 = word2[j - 1]
                temp3 = word3[j - 1]
            word0[j] = word0[j - 4] ^ temp0
            word1[j] = word1[j - 4] ^ temp1
            word2[j] = word2[j - 4] ^ temp2
            word3[j] = word3[j - 4] ^ temp3
            j = j + 1

        # --- AddRoundKey(n=0) ---
        j = 0
        while j < 4:
            st[j * 4] = st[j * 4] ^ word0[j]
            st[1 + j * 4] = st[1 + j * 4] ^ word1[j]
            st[2 + j * 4] = st[2 + j * 4] ^ word2[j]
            st[3 + j * 4] = st[3 + j * 4] ^ word3[j]
            j = j + 1

        # --- Encrypt rounds (enc_round_val=0, loop i=1..9) ---
        i = 1
        while i <= 9:
            # ByteSub_ShiftRow (nb=4)
            temp = sbox[st[1]]
            st[1] = sbox[st[5]]; st[5] = sbox[st[9]]; st[9] = sbox[st[13]]; st[13] = temp
            temp = sbox[st[2]]; st[2] = sbox[st[10]]; st[10] = temp
            temp = sbox[st[6]]; st[6] = sbox[st[14]]; st[14] = temp
            temp = sbox[st[3]]; st[3] = sbox[st[15]]; st[15] = sbox[st[11]]; st[11] = sbox[st[7]]; st[7] = temp
            st[0] = sbox[st[0]]; st[4] = sbox[st[4]]; st[8] = sbox[st[8]]; st[12] = sbox[st[12]]

            # MixColumn_AddRoundKey (nb=4, n=i)
            j = 0
            while j < 4:
                ret[j * 4] = (st[j * 4] << 1)
                if (ret[j * 4] >> 8) == 1:
                    ret[j * 4] = ret[j * 4] ^ 283
                x = st[1 + j * 4]; x = x ^ (x << 1)
                if (x >> 8) == 1:
                    ret[j * 4] = ret[j * 4] ^ (x ^ 283)
                else:
                    ret[j * 4] = ret[j * 4] ^ x
                ret[j * 4] = ret[j * 4] ^ st[2 + j * 4] ^ st[3 + j * 4] ^ word0[j + 4 * i]

                ret[1 + j * 4] = (st[1 + j * 4] << 1)
                if (ret[1 + j * 4] >> 8) == 1:
                    ret[1 + j * 4] = ret[1 + j * 4] ^ 283
                x = st[2 + j * 4]; x = x ^ (x << 1)
                if (x >> 8) == 1:
                    ret[1 + j * 4] = ret[1 + j * 4] ^ (x ^ 283)
                else:
                    ret[1 + j * 4] = ret[1 + j * 4] ^ x
                ret[1 + j * 4] = ret[1 + j * 4] ^ st[3 + j * 4] ^ st[j * 4] ^ word1[j + 4 * i]

                ret[2 + j * 4] = (st[2 + j * 4] << 1)
                if (ret[2 + j * 4] >> 8) == 1:
                    ret[2 + j * 4] = ret[2 + j * 4] ^ 283
                x = st[3 + j * 4]; x = x ^ (x << 1)
                if (x >> 8) == 1:
                    ret[2 + j * 4] = ret[2 + j * 4] ^ (x ^ 283)
                else:
                    ret[2 + j * 4] = ret[2 + j * 4] ^ x
                ret[2 + j * 4] = ret[2 + j * 4] ^ st[j * 4] ^ st[1 + j * 4] ^ word2[j + 4 * i]

                ret[3 + j * 4] = (st[3 + j * 4] << 1)
                if (ret[3 + j * 4] >> 8) == 1:
                    ret[3 + j * 4] = ret[3 + j * 4] ^ 283
                x = st[j * 4]; x = x ^ (x << 1)
                if (x >> 8) == 1:
                    ret[3 + j * 4] = ret[3 + j * 4] ^ (x ^ 283)
                else:
                    ret[3 + j * 4] = ret[3 + j * 4] ^ x
                ret[3 + j * 4] = ret[3 + j * 4] ^ st[1 + j * 4] ^ st[2 + j * 4] ^ word3[j + 4 * i]
                j = j + 1
            j = 0
            while j < 4:
                st[j * 4] = ret[j * 4]
                st[1 + j * 4] = ret[1 + j * 4]
                st[2 + j * 4] = ret[2 + j * 4]
                st[3 + j * 4] = ret[3 + j * 4]
                j = j + 1
            i = i + 1

        # Final ByteSub_ShiftRow
        temp = sbox[st[1]]
        st[1] = sbox[st[5]]; st[5] = sbox[st[9]]; st[9] = sbox[st[13]]; st[13] = temp
        temp = sbox[st[2]]; st[2] = sbox[st[10]]; st[10] = temp
        temp = sbox[st[6]]; st[6] = sbox[st[14]]; st[14] = temp
        temp = sbox[st[3]]; st[3] = sbox[st[15]]; st[15] = sbox[st[11]]; st[11] = sbox[st[7]]; st[7] = temp
        st[0] = sbox[st[0]]; st[4] = sbox[st[4]]; st[8] = sbox[st[8]]; st[12] = sbox[st[12]]

        # Final AddRoundKey(n=10)
        j = 0
        while j < 4:
            st[j * 4] = st[j * 4] ^ word0[j + 40]
            st[1 + j * 4] = st[1 + j * 4] ^ word1[j + 40]
            st[2 + j * 4] = st[2 + j * 4] ^ word2[j + 40]
            st[3 + j * 4] = st[3 + j * 4] ^ word3[j + 40]
            j = j + 1

        # Output encrypted state (16 bytes)
        i = 0
        while i < 16:
            self.statemt_out.wr(st[i])
            i = i + 1

        # ============================================================
        # DECRYPT (type=128128, nb=4, dec_round_val=10)
        # ============================================================
        # KeySchedule already computed, word0..3 unchanged

        # --- AddRoundKey(n=10) ---
        j = 0
        while j < 4:
            st[j * 4] = st[j * 4] ^ word0[j + 40]
            st[1 + j * 4] = st[1 + j * 4] ^ word1[j + 40]
            st[2 + j * 4] = st[2 + j * 4] ^ word2[j + 40]
            st[3 + j * 4] = st[3 + j * 4] ^ word3[j + 40]
            j = j + 1

        # --- InversShiftRow_ByteSub (nb=4) ---
        temp = invsbox[st[13]]
        st[13] = invsbox[st[9]]; st[9] = invsbox[st[5]]; st[5] = invsbox[st[1]]; st[1] = temp
        temp = invsbox[st[14]]; st[14] = invsbox[st[6]]; st[6] = temp
        temp = invsbox[st[2]]; st[2] = invsbox[st[10]]; st[10] = temp
        temp = invsbox[st[15]]; st[15] = invsbox[st[3]]; st[3] = invsbox[st[7]]; st[7] = invsbox[st[11]]; st[11] = temp
        st[0] = invsbox[st[0]]; st[4] = invsbox[st[4]]; st[8] = invsbox[st[8]]; st[12] = invsbox[st[12]]

        # --- Decrypt rounds (i=9..1) ---
        i = 9
        while i >= 1:
            # AddRoundKey_InversMixColumn (nb=4, n=i)
            j = 0
            while j < 4:
                st[j * 4] = st[j * 4] ^ word0[j + 4 * i]
                st[1 + j * 4] = st[1 + j * 4] ^ word1[j + 4 * i]
                st[2 + j * 4] = st[2 + j * 4] ^ word2[j + 4 * i]
                st[3 + j * 4] = st[3 + j * 4] ^ word3[j + 4 * i]
                j = j + 1
            j = 0
            while j < 4:
                # ii=0: 0e*st[0], 0b*st[1], 0d*st[2], 09*st[3]
                x = (st[0 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[0 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[0 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                ret[0 + j * 4] = x
                x = (st[1 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[1 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[1 + j * 4]
                ret[0 + j * 4] = ret[0 + j * 4] ^ x
                x = (st[2 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[2 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[2 + j * 4]
                ret[0 + j * 4] = ret[0 + j * 4] ^ x
                x = (st[3 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[3 + j * 4]
                ret[0 + j * 4] = ret[0 + j * 4] ^ x

                # ii=1: 0e*st[1], 0b*st[2], 0d*st[3], 09*st[0]
                x = (st[1 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[1 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[1 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                ret[1 + j * 4] = x
                x = (st[2 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[2 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[2 + j * 4]
                ret[1 + j * 4] = ret[1 + j * 4] ^ x
                x = (st[3 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[3 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[3 + j * 4]
                ret[1 + j * 4] = ret[1 + j * 4] ^ x
                x = (st[0 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[0 + j * 4]
                ret[1 + j * 4] = ret[1 + j * 4] ^ x

                # ii=2: 0e*st[2], 0b*st[3], 0d*st[0], 09*st[1]
                x = (st[2 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[2 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[2 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                ret[2 + j * 4] = x
                x = (st[3 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[3 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[3 + j * 4]
                ret[2 + j * 4] = ret[2 + j * 4] ^ x
                x = (st[0 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[0 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[0 + j * 4]
                ret[2 + j * 4] = ret[2 + j * 4] ^ x
                x = (st[1 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[1 + j * 4]
                ret[2 + j * 4] = ret[2 + j * 4] ^ x

                # ii=3: 0e*st[3], 0b*st[0], 0d*st[1], 09*st[2]
                x = (st[3 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[3 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[3 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                ret[3 + j * 4] = x
                x = (st[0 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[0 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[0 + j * 4]
                ret[3 + j * 4] = ret[3 + j * 4] ^ x
                x = (st[1 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[1 + j * 4]; x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[1 + j * 4]
                ret[3 + j * 4] = ret[3 + j * 4] ^ x
                x = (st[2 + j * 4] << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = (x << 1)
                if (x >> 8) == 1: x = x ^ 283
                x = x ^ st[2 + j * 4]
                ret[3 + j * 4] = ret[3 + j * 4] ^ x

                j = j + 1
            j = 0
            while j < 4:
                st[j * 4] = ret[j * 4]
                st[1 + j * 4] = ret[1 + j * 4]
                st[2 + j * 4] = ret[2 + j * 4]
                st[3 + j * 4] = ret[3 + j * 4]
                j = j + 1

            # InversShiftRow_ByteSub (nb=4)
            temp = invsbox[st[13]]
            st[13] = invsbox[st[9]]; st[9] = invsbox[st[5]]; st[5] = invsbox[st[1]]; st[1] = temp
            temp = invsbox[st[14]]; st[14] = invsbox[st[6]]; st[6] = temp
            temp = invsbox[st[2]]; st[2] = invsbox[st[10]]; st[10] = temp
            temp = invsbox[st[15]]; st[15] = invsbox[st[3]]; st[3] = invsbox[st[7]]; st[7] = invsbox[st[11]]; st[11] = temp
            st[0] = invsbox[st[0]]; st[4] = invsbox[st[4]]; st[8] = invsbox[st[8]]; st[12] = invsbox[st[12]]

            i = i - 1

        # --- Final AddRoundKey(n=0) ---
        j = 0
        while j < 4:
            st[j * 4] = st[j * 4] ^ word0[j]
            st[1 + j * 4] = st[1 + j * 4] ^ word1[j]
            st[2 + j * 4] = st[2 + j * 4] ^ word2[j]
            st[3 + j * 4] = st[3 + j * 4] ^ word3[j]
            j = j + 1

        # Output decrypted state (16 bytes)
        i = 0
        while i < 16:
            self.statemt_out.wr(st[i])
            i = i + 1


@testbench
def test():
    aes = AES()

    # Input plaintext: statemt
    plaintext = [50, 67, 246, 168, 136, 90, 48, 141, 49, 49, 152, 162, 224, 55, 7, 52]
    for d in plaintext:
        aes.statemt_in.wr(d)
    # Input key
    key = [43, 126, 21, 22, 40, 174, 210, 166, 171, 247, 21, 136, 9, 207, 79, 60]
    for d in key:
        aes.key_in.wr(d)

    # Expected encrypted output
    out_enc = [0x39, 0x25, 0x84, 0x1d, 0x02, 0xdc, 0x09, 0xfb,
               0xdc, 0x11, 0x85, 0x97, 0x19, 0x6a, 0x0b, 0x32]
    # Expected decrypted output (= original plaintext)
    out_dec = [0x32, 0x43, 0xf6, 0xa8, 0x88, 0x5a, 0x30, 0x8d,
               0x31, 0x31, 0x98, 0xa2, 0xe0, 0x37, 0x07, 0x34]

    main_result = 0
    # Check encrypted output
    for i in range(16):
        d = aes.statemt_out.rd()
        print(d)
        main_result += (d != out_enc[i])
    # Check decrypted output
    for i in range(16):
        d = aes.statemt_out.rd()
        print(d)
        main_result += (d != out_dec[i])

    assert 0 == main_result
