from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import List, bit64

MASK64 = 0xFFFFFFFFFFFFFFFF
MASK32 = 0xFFFFFFFF


@module
class DFMUL:
    def __init__(self):
        self.a_in = Handshake(bit64, "in")
        self.b_in = Handshake(bit64, "in")
        self.z_out = Handshake(bit64, "out")
        self.append_worker(self.dfmul_main)

    def packFloat64(self, zSign, zExp, zSig):
        s:bit64 = zSign
        e:bit64 = zExp
        f:bit64 = zSig
        return ((s << 63) + (e << 52) + f) & MASK64

    def shift64RightJamming(self, a, count):
        z:bit64 = 0
        if count == 0:
            z = a
        elif count < 64:
            shifted:bit64 = (a >> count) & MASK64
            rem:bit64 = (a << (64 - count)) & MASK64
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
        roundIncrement:bit64 = 0x200
        roundBits:bit64 = zSig & 0x3FF
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

    def float64_mul(self, a, b):
        aSig:bit64 = a & 0x000FFFFFFFFFFFFF
        aExp = (a >> 52) & 0x7FF
        aSign = (a >> 63) & 1
        bSig:bit64 = b & 0x000FFFFFFFFFFFFF
        bExp = (b >> 52) & 0x7FF
        bSign = (b >> 63) & 1
        zSign = aSign ^ bSign

        if aExp == 0x7FF:
            if aSig != 0:
                return self.propagateFloat64NaN(a, b)
            if (bExp == 0x7FF) and (bSig != 0):
                return self.propagateFloat64NaN(a, b)
            if (bExp | bSig) == 0:
                default_nan:bit64 = 0x7FFFFFFFFFFFFFFF
                return default_nan
            return self.packFloat64(zSign, 0x7FF, 0)

        if bExp == 0x7FF:
            if bSig != 0:
                return self.propagateFloat64NaN(a, b)
            if (aExp | aSig) == 0:
                default_nan2:bit64 = 0x7FFFFFFFFFFFFFFF
                return default_nan2
            return self.packFloat64(zSign, 0x7FF, 0)

        if aExp == 0:
            if aSig == 0:
                return self.packFloat64(zSign, 0, 0)
            sc = self.countLeadingZeros64(aSig) - 11
            aSig = (aSig << sc) & MASK64
            aExp = 1 - sc

        if bExp == 0:
            if bSig == 0:
                return self.packFloat64(zSign, 0, 0)
            sc2 = self.countLeadingZeros64(bSig) - 11
            bSig = (bSig << sc2) & MASK64
            bExp = 1 - sc2

        zExp = aExp + bExp - 0x3FF
        aSig = ((aSig | 0x0010000000000000) << 10) & MASK64
        bSig = ((bSig | 0x0010000000000000) << 11) & MASK64

        # mul64To128 inlined
        aLow:bit64 = aSig & MASK32
        aHigh:bit64 = (aSig >> 32) & MASK32
        bLow:bit64 = bSig & MASK32
        bHigh:bit64 = (bSig >> 32) & MASK32
        z1:bit64 = aLow * bLow
        zMiddleA:bit64 = aLow * bHigh
        zMiddleB:bit64 = aHigh * bLow
        zSig0:bit64 = aHigh * bHigh
        zMiddleA = (zMiddleA + zMiddleB) & MASK64
        carry = 0
        if zMiddleA < zMiddleB:
            carry = 1
        zSig0 = (zSig0 + (carry << 32) + ((zMiddleA >> 32) & MASK32)) & MASK64
        zMiddleA = (zMiddleA << 32) & MASK64
        z1 = (z1 + zMiddleA) & MASK64
        carry2 = 0
        if z1 < zMiddleA:
            carry2 = 1
        zSig0 = (zSig0 + carry2) & MASK64

        if z1 != 0:
            zSig0 = zSig0 | 1

        # check if MSB of (zSig0 << 1) is 0
        if (((zSig0 << 1) & MASK64) >> 63) == 0:
            zSig0 = (zSig0 << 1) & MASK64
            zExp = zExp - 1

        return self.roundAndPackFloat64(zSign, zExp, zSig0)

    def dfmul_main(self):
        i = 0
        while i < 20:
            a = self.a_in.rd()
            b = self.b_in.rd()
            result = self.float64_mul(a, b)
            self.z_out.wr(result)
            i = i + 1


@testbench
def test():
    dfmul = DFMUL()

    a_input:List[bit64] = [
        0x7FF0000000000000, 0x7FFF000000000000, 0x7FF0000000000000, 0x7FF0000000000000,
        0x3FF0000000000000, 0x0000000000000000, 0x3FF0000000000000, 0x0000000000000000,
        0x8000000000000000, 0x3FF0000000000000, 0x3FF0000000000000, 0x4000000000000000,
        0x3FD0000000000000, 0xC000000000000000, 0xBFD0000000000000, 0x4000000000000000,
        0xBFD0000000000000, 0xC000000000000000, 0x3FD0000000000000, 0x0000000000000000,
    ]

    b_input:List[bit64] = [
        0xFFFFFFFFFFFFFFFF, 0xFFF0000000000000, 0x0000000000000000, 0x3FF0000000000000,
        0xFFFF000000000000, 0x7FF0000000000000, 0x7FF0000000000000, 0x3FF0000000000000,
        0x3FF0000000000000, 0x0000000000000000, 0x8000000000000000, 0x3FD0000000000000,
        0x4000000000000000, 0xBFD0000000000000, 0xC000000000000000, 0xBFD0000000000000,
        0x4000000000000000, 0x3FD0000000000000, 0xC000000000000000, 0x0000000000000000,
    ]

    z_output:List[bit64] = [
        0xFFFFFFFFFFFFFFFF, 0x7FFF000000000000, 0x7FFFFFFFFFFFFFFF, 0x7FF0000000000000,
        0xFFFF000000000000, 0x7FFFFFFFFFFFFFFF, 0x7FF0000000000000, 0x0000000000000000,
        0x8000000000000000, 0x0000000000000000, 0x8000000000000000, 0x3FE0000000000000,
        0x3FE0000000000000, 0x3FE0000000000000, 0x3FE0000000000000, 0xBFE0000000000000,
        0xBFE0000000000000, 0xBFE0000000000000, 0xBFE0000000000000, 0x0000000000000000,
    ]

    main_result = 0
    for i in range(20):
        dfmul.a_in.wr(a_input[i])
        dfmul.b_in.wr(b_input[i])
        result = dfmul.z_out.rd()
        print(result)
        main_result += (result != z_output[i])

    assert 0 == main_result
