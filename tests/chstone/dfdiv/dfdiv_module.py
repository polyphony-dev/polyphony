from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import List, bit64

MASK64 = 0xFFFFFFFFFFFFFFFF
MASK32 = 0xFFFFFFFF


@module
class DFDIV:
    def __init__(self):
        self.a_in = Handshake(bit64, "in")
        self.b_in = Handshake(bit64, "in")
        self.z_out = Handshake(bit64, "out")
        self.append_worker(self.dfdiv_main)

    def packFloat64(self, zSign, zExp, zSig):
        s: bit64 = zSign
        e: bit64 = zExp
        f: bit64 = zSig
        return ((s << 63) + (e << 52) + f) & MASK64

    def shift64RightJamming(self, a, count):
        z: bit64 = 0
        if count == 0:
            z = a
        elif count < 64:
            shifted: bit64 = (a >> count) & MASK64
            rem: bit64 = (a << (64 - count)) & MASK64
            if rem != 0:
                z = shifted | 1
            else:
                z = shifted
        else:
            if a != 0:
                z = 1
            else:
                z = 0
        return z

    def countLeadingZeros64(self, a):
        countLeadingZerosHigh = [
            8,
            7,
            6,
            6,
            5,
            5,
            5,
            5,
            4,
            4,
            4,
            4,
            4,
            4,
            4,
            4,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            3,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            2,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
        shiftCount = 0
        if a < 0x100000000:
            shiftCount = 32
        else:
            a = (a >> 32) & MASK32
        if a < 0x10000:
            shiftCount = shiftCount + 16
            a = (a << 16) & MASK32
        if a < 0x1000000:
            shiftCount = shiftCount + 8
            a = (a << 8) & MASK32
        shiftCount = shiftCount + countLeadingZerosHigh[(a >> 24) & 0xFF]
        return shiftCount

    def propagateFloat64NaN(self, a, b):
        aIsSignalingNaN = 0
        if ((a >> 51) & 0xFFF) == 0xFFE:
            if (a & 0x0007FFFFFFFFFFFF) != 0:
                aIsSignalingNaN = 1
        bIsNaN = 0
        if ((b >> 52) & 0x7FF) == 0x7FF:
            if (b & 0x000FFFFFFFFFFFFF) != 0:
                bIsNaN = 1
        bIsSignalingNaN = 0
        if ((b >> 51) & 0xFFF) == 0xFFE:
            if (b & 0x0007FFFFFFFFFFFF) != 0:
                bIsSignalingNaN = 1
        a = a | 0x0008000000000000
        b = b | 0x0008000000000000
        if bIsSignalingNaN:
            return b
        if aIsSignalingNaN:
            return a
        if bIsNaN:
            return b
        return a

    def roundAndPackFloat64(self, zSign, zExp, zSig):
        roundIncrement: bit64 = 0x200
        roundBits: bit64 = zSig & 0x3FF
        need_special = 0
        if zExp < 0:
            need_special = 1
        if zExp >= 0x7FD:
            need_special = 1
        if need_special:
            if zExp > 0x7FD:
                return self.packFloat64(zSign, 0x7FF, 0)
            if zExp == 0x7FD:
                if ((zSig + roundIncrement) >> 63) & 1:
                    return self.packFloat64(zSign, 0x7FF, 0)
            if zExp < 0:
                zSig = self.shift64RightJamming(zSig, 0 - zExp)
                zExp = 0
                roundBits = zSig & 0x3FF
        zSig = ((zSig + roundIncrement) >> 10) & MASK64
        if roundBits == 0x200:
            zSig = zSig & 0xFFFFFFFFFFFFFFFE
        if zSig == 0:
            zExp = 0
        return self.packFloat64(zSign, zExp, zSig)

    def mul64To128_z0(self, a, b):
        aLow: bit64 = a & MASK32
        aHigh: bit64 = (a >> 32) & MASK32
        bLow: bit64 = b & MASK32
        bHigh: bit64 = (b >> 32) & MASK32
        z1: bit64 = aLow * bLow
        zMiddleA: bit64 = aLow * bHigh
        zMiddleB: bit64 = aHigh * bLow
        z0: bit64 = aHigh * bHigh
        zMiddleA = (zMiddleA + zMiddleB) & MASK64
        carry = 0
        if zMiddleA < zMiddleB:
            carry = 1
        z0 = (z0 + (carry << 32) + ((zMiddleA >> 32) & MASK32)) & MASK64
        zMiddleA = (zMiddleA << 32) & MASK64
        z1 = (z1 + zMiddleA) & MASK64
        carry2 = 0
        if z1 < zMiddleA:
            carry2 = 1
        z0 = (z0 + carry2) & MASK64
        return z0

    def mul64To128_z1(self, a, b):
        aLow: bit64 = a & MASK32
        aHigh: bit64 = (a >> 32) & MASK32
        bLow: bit64 = b & MASK32
        bHigh: bit64 = (b >> 32) & MASK32
        z1: bit64 = aLow * bLow
        zMiddleA: bit64 = aLow * bHigh
        zMiddleB: bit64 = aHigh * bLow
        zMiddleA = (zMiddleA + zMiddleB) & MASK64
        zMiddleA = (zMiddleA << 32) & MASK64
        z1 = (z1 + zMiddleA) & MASK64
        return z1

    def estimateDiv128To64(self, a0, a1, b):
        if b <= a0:
            return MASK64
        b0: bit64 = (b >> 32) & MASK32

        z: bit64 = 0
        if (b0 << 32) <= a0:
            z = 0xFFFFFFFF00000000
        else:
            z = ((a0 // b0) << 32) & MASK64

        term0: bit64 = self.mul64To128_z0(b, z)
        term1: bit64 = self.mul64To128_z1(b, z)

        # sub128(a0, a1, term0, term1)
        rem1: bit64 = (a1 - term1) & MASK64
        borrow = 0
        if a1 < term1:
            borrow = 1
        rem0: bit64 = (a0 - term0 - borrow) & MASK64

        # while (sbits64)rem0 < 0
        while (rem0 >> 63) & 1:
            z = (z - 0x100000000) & MASK64
            b1: bit64 = (b << 32) & MASK64
            # add128(rem0, rem1, b0, b1)
            new_rem1: bit64 = (rem1 + b1) & MASK64
            carry = 0
            if new_rem1 < rem1:
                carry = 1
            rem0 = (rem0 + b0 + carry) & MASK64
            rem1 = new_rem1

        rem0 = ((rem0 << 32) | ((rem1 >> 32) & MASK32)) & MASK64
        if (b0 << 32) <= rem0:
            z = z | 0xFFFFFFFF
        else:
            z = z | (rem0 // b0)
        return z & MASK64

    def float64_div(self, a, b):
        aSig: bit64 = a & 0x000FFFFFFFFFFFFF
        aExp = (a >> 52) & 0x7FF
        aSign = (a >> 63) & 1
        bSig: bit64 = b & 0x000FFFFFFFFFFFFF
        bExp = (b >> 52) & 0x7FF
        bSign = (b >> 63) & 1
        zSign = aSign ^ bSign

        if aExp == 0x7FF:
            if aSig != 0:
                return self.propagateFloat64NaN(a, b)
            if bExp == 0x7FF:
                if bSig != 0:
                    return self.propagateFloat64NaN(a, b)
                default_nan: bit64 = 0x7FFFFFFFFFFFFFFF
                return default_nan
            return self.packFloat64(zSign, 0x7FF, 0)

        if bExp == 0x7FF:
            if bSig != 0:
                return self.propagateFloat64NaN(a, b)
            return self.packFloat64(zSign, 0, 0)

        if bExp == 0:
            if bSig == 0:
                if (aExp | aSig) == 0:
                    default_nan2: bit64 = 0x7FFFFFFFFFFFFFFF
                    return default_nan2
                return self.packFloat64(zSign, 0x7FF, 0)
            sc = self.countLeadingZeros64(bSig) - 11
            bSig = (bSig << sc) & MASK64
            bExp = 1 - sc

        if aExp == 0:
            if aSig == 0:
                return self.packFloat64(zSign, 0, 0)
            sc2 = self.countLeadingZeros64(aSig) - 11
            aSig = (aSig << sc2) & MASK64
            aExp = 1 - sc2

        zExp = aExp - bExp + 0x3FD
        aSig = ((aSig | 0x0010000000000000) << 10) & MASK64
        bSig = ((bSig | 0x0010000000000000) << 11) & MASK64

        if bSig <= ((aSig + aSig) & MASK64):
            aSig = (aSig >> 1) & MASK64
            zExp = zExp + 1

        zSig: bit64 = self.estimateDiv128To64(aSig, 0, bSig)

        if (zSig & 0x1FF) <= 2:
            # mul64To128(bSig, zSig)
            term0: bit64 = self.mul64To128_z0(bSig, zSig)
            term1: bit64 = self.mul64To128_z1(bSig, zSig)
            # sub128(aSig, 0, term0, term1)
            rem1: bit64 = (0 - term1) & MASK64
            borrow = 0
            if term1 > 0:
                borrow = 1
            rem0: bit64 = (aSig - term0 - borrow) & MASK64
            while (rem0 >> 63) & 1:
                zSig = (zSig - 1) & MASK64
                # add128(rem0, rem1, 0, bSig)
                new_rem1: bit64 = (rem1 + bSig) & MASK64
                carry = 0
                if new_rem1 < rem1:
                    carry = 1
                rem0 = (rem0 + carry) & MASK64
                rem1 = new_rem1
            if rem1 != 0:
                zSig = zSig | 1

        return self.roundAndPackFloat64(zSign, zExp, zSig)

    def dfdiv_main(self):
        i = 0
        while i < 22:
            a = self.a_in.rd()
            b = self.b_in.rd()
            result = self.float64_div(a, b)
            self.z_out.wr(result)
            i = i + 1


@testbench
def test():
    dfdiv = DFDIV()

    a_input: List[bit64] = [
        0x7FFF000000000000,
        0x7FF0000000000000,
        0x7FF0000000000000,
        0x7FF0000000000000,
        0x3FF0000000000000,
        0x3FF0000000000000,
        0x0000000000000000,
        0x3FF0000000000000,
        0x0000000000000000,
        0x8000000000000000,
        0x4008000000000000,
        0xC008000000000000,
        0x4008000000000000,
        0xC008000000000000,
        0x4000000000000000,
        0xC000000000000000,
        0x4000000000000000,
        0xC000000000000000,
        0x3FF0000000000000,
        0xBFF0000000000000,
        0x3FF0000000000000,
        0xBFF0000000000000,
    ]

    b_input: List[bit64] = [
        0x3FF0000000000000,
        0x7FF8000000000000,
        0x7FF0000000000000,
        0x3FF0000000000000,
        0x7FF8000000000000,
        0x7FF0000000000000,
        0x0000000000000000,
        0x0000000000000000,
        0x3FF0000000000000,
        0x3FF0000000000000,
        0x4000000000000000,
        0x4000000000000000,
        0xC000000000000000,
        0xC000000000000000,
        0x4010000000000000,
        0x4010000000000000,
        0xC010000000000000,
        0xC010000000000000,
        0x3FF8000000000000,
        0x3FF8000000000000,
        0xBFF8000000000000,
        0xBFF8000000000000,
    ]

    z_output: List[bit64] = [
        0x7FFF000000000000,
        0x7FF8000000000000,
        0x7FFFFFFFFFFFFFFF,
        0x7FF0000000000000,
        0x7FF8000000000000,
        0x0000000000000000,
        0x7FFFFFFFFFFFFFFF,
        0x7FF0000000000000,
        0x0000000000000000,
        0x8000000000000000,
        0x3FF8000000000000,
        0xBFF8000000000000,
        0xBFF8000000000000,
        0x3FF8000000000000,
        0x3FE0000000000000,
        0xBFE0000000000000,
        0xBFE0000000000000,
        0x3FE0000000000000,
        0x3FE5555555555555,
        0xBFE5555555555555,
        0xBFE5555555555555,
        0x3FE5555555555555,
    ]

    main_result = 0
    for i in range(22):
        dfdiv.a_in.wr(a_input[i])
        dfdiv.b_in.wr(b_input[i])
        result = dfdiv.z_out.rd()
        print(result)
        main_result += (result != z_output[i])

    assert 0 == main_result
