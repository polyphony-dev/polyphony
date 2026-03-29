"""Tests for polyphony.compiler.bits (Bits and GenericMeta)."""
import pytest


# bits.py has module-level print statements, so we import the classes directly
# by loading the module content without executing print statements.
# Actually, we need to just import and let the prints happen (they go to stdout).
# pytest captures stdout by default so this is fine.
from polyphony.compiler.bits import Bits, GenericMeta


class TestGenericMeta:
    def test_subscript_creates_class(self):
        B4 = Bits[4]
        assert B4.width == 4

    def test_different_widths(self):
        B8 = Bits[8]
        B16 = Bits[16]
        assert B8.width == 8
        assert B16.width == 16


class TestBitsInit:
    def test_basic(self):
        B4 = Bits[4]
        v = B4(0b1010)
        assert v.value == 0b1010

    def test_mask_applied(self):
        B4 = Bits[4]
        v = B4(0b11111111)  # only lower 4 bits
        assert v.value == 0b1111

    def test_zero(self):
        B8 = Bits[8]
        v = B8(0)
        assert v.value == 0

    def test_default_init(self):
        B4 = Bits[4]
        v = B4()
        assert v.value == 0


class TestBitsGetitem:
    def test_single_bit(self):
        B4 = Bits[4]
        v = B4(0b1010)
        assert int(v[0]) == 0
        assert int(v[1]) == 1
        assert int(v[2]) == 0
        assert int(v[3]) == 1

    def test_single_bit_width(self):
        B4 = Bits[4]
        v = B4(0b1010)
        assert len(v[0]) == 1

    def test_slice(self):
        B4 = Bits[4]
        v = B4(0b1100)
        s = v[0:2]
        assert int(s) == 0b00
        assert len(s) == 2

    def test_slice_upper(self):
        B4 = Bits[4]
        v = B4(0b1100)
        s = v[2:4]
        assert int(s) == 0b11
        assert len(s) == 2


class TestBitsInt:
    def test_int(self):
        B8 = Bits[8]
        v = B8(42)
        assert int(v) == 42


class TestBitsStr:
    def test_str(self):
        B4 = Bits[4]
        v = B4(0b0110)
        s = str(v)
        assert '0110' in s


class TestBitsLen:
    def test_len(self):
        B8 = Bits[8]
        v = B8(0)
        assert len(v) == 8


class TestBitsAdd:
    def test_concat(self):
        B2 = Bits[2]
        a = B2(0b01)
        b = B2(0b10)
        c = a + b
        assert len(c) == 4
        # a is lower bits, b is upper bits: b << 2 | a = 0b1001
        assert int(c) == 0b1001


class TestBitsAnd:
    def test_and_int(self):
        B4 = Bits[4]
        v = B4(0b1100)
        r = v & 0b1010
        assert int(r) == 0b1000
        assert len(r) == 4

    def test_and_bits(self):
        B4 = Bits[4]
        a = B4(0b1100)
        b = B4(0b1010)
        r = a & b
        assert int(r) == 0b1000


class TestBitsOr:
    def test_or_int(self):
        B4 = Bits[4]
        v = B4(0b1100)
        r = v | 0b0011
        assert int(r) == 0b1111

    def test_or_bits(self):
        B4 = Bits[4]
        a = B4(0b1100)
        b = B4(0b0011)
        r = a | b
        assert int(r) == 0b1111


class TestBitsXor:
    def test_xor_int(self):
        B4 = Bits[4]
        v = B4(0b1100)
        r = v ^ 0b1010
        assert int(r) == 0b0110

    def test_xor_bits(self):
        B4 = Bits[4]
        a = B4(0b1100)
        b = B4(0b1010)
        r = a ^ b
        assert int(r) == 0b0110
