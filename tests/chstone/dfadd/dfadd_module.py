from polyphony import testbench
from polyphony import module
from polyphony.modules import Handshake
from polyphony.typing import List, bit64

MASK64 = 0xFFFFFFFFFFFFFFFF


@module
class DFADD:
    def __init__(self):
        self.a_in = Handshake(bit64, "in")
        self.b_in = Handshake(bit64, "in")
        self.z_out = Handshake(bit64, "out")
        self.append_worker(self.dfadd_main)

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
            a = (a >> 32) & 0xFFFFFFFF
        if a < 0x10000:
            shiftCount = shiftCount + 16
            a = (a << 16) & 0xFFFFFFFF
        if a < 0x1000000:
            shiftCount = shiftCount + 8
            a = (a << 8) & 0xFFFFFFFF
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

    def addFloat64Sigs(self, a, b, zSign):
        aSig:bit64 = a & 0x000FFFFFFFFFFFFF
        aExp = (a >> 52) & 0x7FF
        bSig:bit64 = b & 0x000FFFFFFFFFFFFF
        bExp = (b >> 52) & 0x7FF
        expDiff = aExp - bExp
        aSig = (aSig << 9) & MASK64
        bSig = (bSig << 9) & MASK64

        zSig:bit64 = 0
        zExp:bit64 = 0
        skip = 0

        if expDiff > 0:
            if aExp == 0x7FF:
                if aSig != 0:
                    return self.propagateFloat64NaN(a, b)
                return a
            if bExp == 0:
                expDiff = expDiff - 1
            else:
                bSig = bSig | 0x2000000000000000
            bSig = self.shift64RightJamming(bSig, expDiff)
            zExp = aExp
        elif expDiff < 0:
            if bExp == 0x7FF:
                if bSig != 0:
                    return self.propagateFloat64NaN(a, b)
                return self.packFloat64(zSign, bExp, 0)
            if aExp == 0:
                expDiff = expDiff + 1
            else:
                aSig = aSig | 0x2000000000000000
            aSig = self.shift64RightJamming(aSig, 0 - expDiff)
            zExp = bExp
        else:
            if aExp == 0x7FF:
                if (aSig | bSig) != 0:
                    return self.propagateFloat64NaN(a, b)
                return a
            if aExp == 0:
                return self.packFloat64(zSign, 0, ((aSig + bSig) >> 9) & MASK64)
            zSig = (0x4000000000000000 + aSig + bSig) & MASK64
            zExp = aExp
            skip = 1

        if skip == 0:
            aSig = aSig | 0x2000000000000000
            zSig = ((aSig + bSig) << 1) & MASK64
            zExp = zExp - 1
            if (zSig >> 63) & 1:
                zSig = (aSig + bSig) & MASK64
                zExp = zExp + 1

        return self.roundAndPackFloat64(zSign, zExp, zSig)

    def subFloat64Sigs(self, a, b, zSign):
        aSig:bit64 = a & 0x000FFFFFFFFFFFFF
        aExp:bit64 = (a >> 52) & 0x7FF
        bSig:bit64 = b & 0x000FFFFFFFFFFFFF
        bExp:bit64 = (b >> 52) & 0x7FF
        expDiff = aExp - bExp
        aSig = (aSig << 10) & MASK64
        bSig = (bSig << 10) & MASK64

        zSig:bit64 = 0
        zExp:bit64 = 0

        if expDiff > 0:
            if aExp == 0x7FF:
                if aSig != 0:
                    return self.propagateFloat64NaN(a, b)
                return a
            if bExp == 0:
                expDiff = expDiff - 1
            else:
                bSig = bSig | 0x4000000000000000
            bSig = self.shift64RightJamming(bSig, expDiff)
            aSig = aSig | 0x4000000000000000
            zSig = (aSig - bSig) & MASK64
            zExp = aExp
        elif expDiff < 0:
            if bExp == 0x7FF:
                if bSig != 0:
                    return self.propagateFloat64NaN(a, b)
                return self.packFloat64(zSign ^ 1, bExp, 0)
            if aExp == 0:
                expDiff = expDiff + 1
            else:
                aSig = aSig | 0x4000000000000000
            aSig = self.shift64RightJamming(aSig, 0 - expDiff)
            bSig = bSig | 0x4000000000000000
            zSig = (bSig - aSig) & MASK64
            zExp = bExp
            zSign = zSign ^ 1
        else:
            if aExp == 0x7FF:
                if (aSig | bSig) != 0:
                    return self.propagateFloat64NaN(a, b)
                default_nan:bit64 = 0x7FFFFFFFFFFFFFFF
                return default_nan
            if aExp == 0:
                aExp = 1
                bExp = 1
            if bSig < aSig:
                zSig = (aSig - bSig) & MASK64
                zExp = aExp
            elif aSig < bSig:
                zSig = (bSig - aSig) & MASK64
                zExp = bExp
                zSign = zSign ^ 1
            else:
                return self.packFloat64(0, 0, 0)

        zExp = zExp - 1
        shiftCount = self.countLeadingZeros64(zSig) - 1
        return self.roundAndPackFloat64(zSign, zExp - shiftCount, (zSig << shiftCount) & MASK64)

    def float64_add(self, a, b):
        aSign = (a >> 63) & 1
        bSign = (b >> 63) & 1
        if aSign == bSign:
            return self.addFloat64Sigs(a, b, aSign)
        else:
            return self.subFloat64Sigs(a, b, aSign)

    def dfadd_main(self):
        i = 0
        while i < 46:
            a = self.a_in.rd()
            b = self.b_in.rd()
            result = self.float64_add(a, b)
            self.z_out.wr(result)
            i = i + 1


@testbench
def test():
    dfadd = DFADD()

    a_input:List[bit64] = [
        0x7FF8000000000000, 0x7FF0000000000000, 0x4000000000000000, 0x4000000000000000,
        0x3FF0000000000000, 0x3FF0000000000000, 0x0000000000000000, 0x3FF8000000000000,
        0x7FF8000000000000, 0x7FF0000000000000, 0x0000000000000000, 0x3FF8000000000000,
        0xFFF8000000000000, 0xFFF0000000000000, 0xC000000000000000, 0xC000000000000000,
        0xBFF0000000000000, 0xBFF0000000000000, 0x8000000000000000, 0xBFF8000000000000,
        0xFFF8000000000000, 0xFFF0000000000000, 0x8000000000000000, 0xBFF8000000000000,
        0x7FF8000000000000, 0x7FF0000000000000, 0x3FF0000000000000, 0x3FF0000000000000,
        0x3FF0000000000000, 0x0000000000000000, 0x3FF8000000000000, 0x7FF8000000000000,
        0x7FF0000000000000, 0x3FF0000000000000, 0x4000000000000000, 0xFFF0000000000000,
        0xFFF0000000000000, 0xBFF0000000000000, 0xBFF0000000000000, 0xBFF0000000000000,
        0x8000000000000000, 0xBFF8000000000000, 0xFFF8000000000000, 0xFFF0000000000000,
        0xBFF0000000000000, 0xC000000000000000,
    ]

    b_input:List[bit64] = [
        0x3FF0000000000000, 0x3FF0000000000000, 0x0000000000000000, 0x3FF8000000000000,
        0x7FF8000000000000, 0x7FF0000000000000, 0x4000000000000000, 0x4000000000000000,
        0x7FF0000000000000, 0x7FF0000000000000, 0x0000000000000000, 0x3FF0000000000000,
        0xBFF0000000000000, 0xBFF0000000000000, 0x8000000000000000, 0xBFF8000000000000,
        0xFFF8000000000000, 0xFFF0000000000000, 0xC000000000000000, 0xC000000000000000,
        0xFFF0000000000000, 0xFFF0000000000000, 0x8000000000000000, 0xBFF0000000000000,
        0xFFF0000000000000, 0xFFF0000000000000, 0xBFF0000000000000, 0xFFF8000000000000,
        0xFFF0000000000000, 0xBFF0000000000000, 0xC000000000000000, 0xBFF0000000000000,
        0xBFF0000000000000, 0x8000000000000000, 0xBFF8000000000000, 0x7FF8000000000000,
        0x7FF0000000000000, 0x3FF0000000000000, 0x7FF8000000000000, 0x7FF0000000000000,
        0x3FF0000000000000, 0x4000000000000000, 0x3FF0000000000000, 0x3FF0000000000000,
        0x0000000000000000, 0x3FF8000000000000,
    ]

    z_output:List[bit64] = [
        0x7FF8000000000000, 0x7FF0000000000000, 0x4000000000000000, 0x400C000000000000,
        0x7FF8000000000000, 0x7FF0000000000000, 0x4000000000000000, 0x400C000000000000,
        0x7FF8000000000000, 0x7FF0000000000000, 0x0000000000000000, 0x4004000000000000,
        0xFFF8000000000000, 0xFFF0000000000000, 0xC000000000000000, 0xC00C000000000000,
        0xFFF8000000000000, 0xFFF0000000000000, 0xC000000000000000, 0xC00C000000000000,
        0xFFF8000000000000, 0xFFF0000000000000, 0x8000000000000000, 0xC004000000000000,
        0x7FF8000000000000, 0x7FFFFFFFFFFFFFFF, 0x0000000000000000, 0xFFF8000000000000,
        0xFFF0000000000000, 0xBFF0000000000000, 0xBFE0000000000000, 0x7FF8000000000000,
        0x7FF0000000000000, 0x3FF0000000000000, 0x3FE0000000000000, 0x7FF8000000000000,
        0x7FFFFFFFFFFFFFFF, 0x0000000000000000, 0x7FF8000000000000, 0x7FF0000000000000,
        0x3FF0000000000000, 0x3FE0000000000000, 0xFFF8000000000000, 0xFFF0000000000000,
        0xBFF0000000000000, 0xBFE0000000000000,
    ]

    main_result = 0
    for i in range(46):
        dfadd.a_in.wr(a_input[i])
        dfadd.b_in.wr(b_input[i])
        result = dfadd.z_out.rd()
        print(result)
        main_result += (result != z_output[i])

    assert 0 == main_result
