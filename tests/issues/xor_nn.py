from polyphony import testbench, module
from polyphony.io import Port
from polyphony.modules import Handshake
from polyphony import Channel
from polyphony.typing import List, Tuple, bit, bit8, bit32, bit23, bit24, bit25, bit48
from polyphony.timing import timed


@module
class xor_nn:
    def __init__(self):
        self.a = Port(bit32, 'in')
        self.b = Port(bit32, 'in')
        self.ch_i = Channel(bit32)
        self.ch_o = Channel(bit32)
        self.c = Handshake(bit, 'out')
        self.append_worker(self.io_worker, loop=True)
        self.append_worker(self.predict_worker, loop=True)
        self.w10:Tuple[bit32] = (
            0xc05df563,
            0x3ec21c26,
            0xbfbc4e80,
            0x400e61b5,
            0x4014108f,
            0x4030cc4c,
            0xbfeafa2f,
            0xbf93c7ae
        )
        self.w11:Tuple[bit32] = (
            0x400ca919,
            0x3e943c8e,
            0x4005a4ed,
            0xbfac2bb0,
            0xbfb52db3,
            0x3ff676e0,
            0x40525a13,
            0x3ffa6f50
        )
        self.b1:Tuple[bit32] = (
            0xbf28bc6e,
            0x3ec5db95,
            0x3eff1f0e,
            0x3ebdd38f,
            0x3ecbe433,
            0xbeb8f550,
            0x3edb629c,
            0x3e8a5300
        )
        self.w2:Tuple[bit32] = (
            0x3fb75c24,
            0x3f4a87f9,
            0xc01345c9,
            0xbfe175f0,
            0xc01c6dc7,
            0x407e177e,
            0xbfeb2b6f,
            0xbfae9be5,
        )
        self.b2:bit32 = 0x3f6db6dd
        self.tanht:Tuple[bit32] = (
            0xbf7f0bb0,
            0xbf7e8cf1,
            0xbf7dccba,
            0xbf7ca996,
            0xbf7af177,
            0xbf785a09,
            0xbf747658,
            0xbf6ea9b9,
            0xbf66197c,
            0xbf59a267,
            0xbf47dce7,
            0xbf2f433d,
            0xbf0e908f,
            0xbecabea1,
            0xbe536260,
            0xa6000000,
            0x3e536260,
            0x3ecabea1,
            0x3f0e908f,
            0x3f2f433d,
            0x3f47dce7,
            0x3f59a267,
            0x3f66197c,
            0x3f6ea9b9,
            0x3f747658,
            0x3f785a09,
            0x3f7af177,
            0x3f7ca996,
            0x3f7dccba,
            0x3f7e8cf1,
            0x3f7f0bb0
        )
        self.sigmoidt:Tuple[bit32] = (
            0x3d29ac09,
            0x3d4f341f,
            0x3d7c80d6,
            0x3d997663,
            0x3db9f86f,
            0x3de08c65,
            0x3e06fc01,
            0x3e217985,
            0x3e400a67,
            0x3e62dee1,
            0x3e84ffbc,
            0x3e9aa0af,
            0x3eb21ee3,
            0x3ecb2768,
            0x3ee54a10,
            0x3f000000,
            0x3f0d5af8,
            0x3f1a6c4c,
            0x3f26f08e,
            0x3f32afa8,
            0x3f3d8022,
            0x3f474848,
            0x3f4ffd66,
            0x3f57a19f,
            0x3f5e4100,
            0x3f63ee73,
            0x3f68c0f2,
            0x3f6cd134,
            0x3f7037f3,
            0x3f730cbe,
            0x3f75653f
        )

    @timed
    def io_worker(self):
        x0 = self.a.rd()
        x1 = self.b.rd()
        self.ch_i.put(x0)
        self.ch_i.put(x1)
        y = self.ch_o.get()
        self.c.wr(y)

    def float2b(self, a:bit32):
        a_sig:bit = (a >> 31) & 0x1
        a_exp:bit8 = (a >> 23) & 0xff
        a_fra:bit24 = a & 0x7fffff | 0x800000
        if a_fra == 0x800000:
            a_fra = 0x000000
        return (a_sig, a_exp, a_fra)

    def b2float(self, a_sig:bit32, a_exp:bit32, a_fra:bit32):
        return (a_sig << 31) | (a_exp << 23) | a_fra

    def gt(self, a0:bit32, b0:bit32):
        c0:bit = 0
        if (a0 < b0):
            c0 = 1
        return c0

    def add(self, a0:bit32, b0:bit32):
        (a_sig, a_exp, a_fra) = self.float2b(a0)
        (b_sig, b_exp, b_fra) = self.float2b(b0)
        if a_exp > b_exp:
            (a_sig, b_sig) = (b_sig, a_sig)
            (a_exp, b_exp) = (b_exp, a_exp)
            (a_fra, b_fra) = (b_fra, a_fra)
        if a_exp != b_exp:
            a_fra >>= (b_exp - a_exp)
        sig:bit = a_sig ^ b_sig
        fra:bit23
        frac:bit25
        if sig == 1:
            frac = a_fra - b_fra
            if frac == 0x000000:
                frac = 0
                b_exp = 0
            else:
                while ((frac & 0x800000) < 1):
                    frac <<= 1
                    b_exp -= 1
        else:
            frac = a_fra + b_fra
            if frac & 0x1000000:
                frac = frac >> 1
                b_exp += 1
        fra = frac & 0x7fffff
        c0:bit32 = self.b2float(b_sig, b_exp, fra)
        return c0

    def mul(self, a0:bit32, b0:bit32):
        if (a0 == 0x00000000):
            return a0
        if (b0 == 0x00000000):
            return b0
        (a_sig, a_exp, a_fra) = self.float2b(a0)
        (b_sig, b_exp, b_fra) = self.float2b(b0)
        b_exp = a_exp + b_exp - 127
        b_exp = b_exp & 0xff
        fra:bit23
        frac:bit48 = a_fra * b_fra
        frac = frac >> 23
        while (frac & 0xffffff000000):
            frac = frac >> 1
            b_exp += 1
        fra = frac & 0x7fffff
        b_sig = a_sig ^ b_sig
        c0:bit32 = self.b2float(b_sig, b_exp, fra)
        return c0

    def tanh(self, b0:bit32):
        b0 = self.mul(b0, 0x40A00000)
        b0 = self.add(b0, 0x41700000)
        (b_sig, b_exp, b_fra) = self.float2b(b0)
        b_exp = 127 - b_exp + 23
        b_exp = b_exp & 0xff
        frac:bit48 = b_fra
        frac = frac >> b_exp
        frac = frac & 0xffffff
        if (frac < 31):
            frac = self.tanht[frac]
        c0:bit32 = frac
        return c0

    def sigmoid(self, b0:bit32):
        b0 = self.mul(b0, 0x40A00000)
        b0 = self.add(b0, 0x41700000)
        (b_sig, b_exp, b_fra) = self.float2b(b0)
        b_exp = 127 - b_exp + 23
        b_exp = b_exp & 0xff
        frac:bit48 = b_fra
        frac = frac >> b_exp
        frac = frac & 0xffffff
        if (frac < 31):
            frac = self.sigmoidt[frac]
        c0:bit32 = frac
        return c0

    def predict_worker(self):
        x0 = self.ch_i.get()
        x1 = self.ch_i.get()
        y:bit32 = 0x00000000
        h:List[bit32] = [
            0x00000000, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x0000000, 0x0000000, 0x00000000
        ]
        for l in range(8):
            h[l] = self.add(h[l], self.mul(x0, self.w10[l]))
        for l in range(8):
            h[l] = self.add(h[l], self.mul(x1, self.w11[l]))
        for l in range(8):
            h[l] = self.add(h[l], self.b1[l])
            h[l] = self.tanh(h[l])
        for l in range(8):
            y = self.add(y, self.mul(h[l], self.w2[l]))
        y = self.add(y, self.b2)
        y = self.sigmoid(y)

        v = 0 if self.gt(y, 0x3e99999a) else 1
        self.ch_o.put(v)


@timed
@testbench
def test():
    m = xor_nn()
    m.a.wr(0x00000000)
    m.b.wr(0x00000000)
    c = m.c.rd()
    print("0, 0=", c)
    assert c == 0
    m.a.wr(0x00000000)
    m.b.wr(0x3F800000)
    c = m.c.rd()
    print("0, 1=", c)
    assert c == 1
    m.a.wr(0x3F800000)
    m.b.wr(0x00000000)
    c = m.c.rd()
    print("1, 0=", c)
    assert c == 1
    m.a.wr(0x3F800000)
    m.b.wr(0x3F800000)
    c = m.c.rd()
    print("1, 1=", c)
    assert c == 0
