"""Unit tests for polyphony.simulator Integer class."""
import operator
import pytest
from unittest.mock import MagicMock
from polyphony.simulator import Integer, Value, twos_comp, Simulator


# --- twos_comp ---

class TestTwosComp:
    def test_positive_no_change(self):
        assert twos_comp(5, 8) == 5

    def test_sign_bit_set(self):
        # 0x80 in 8-bit → -128
        assert twos_comp(0x80, 8) == -128

    def test_max_unsigned(self):
        # 0xFF in 8-bit → -1
        assert twos_comp(0xFF, 8) == -1

    def test_64bit_sign_bit(self):
        assert twos_comp(0x8000000000000000, 64) == -9223372036854775808

    def test_64bit_no_sign(self):
        assert twos_comp(0x7FFFFFFFFFFFFFFF, 64) == 0x7FFFFFFFFFFFFFFF


# --- Integer basics ---

class TestIntegerBasics:
    def test_create_unsigned(self):
        i = Integer(42, 32, False)
        assert i.val == 42
        assert i.width == 32
        assert i.sign == False

    def test_create_signed_positive(self):
        i = Integer(42, 32, True)
        assert i.val == 42

    def test_create_signed_negative(self):
        # 0x80000000 in 32-bit signed → -2147483648
        i = Integer(0x80000000, 32, True)
        assert i.val == -2147483648

    def test_create_unsigned_bit63(self):
        # 0x8000000000000000 in 64-bit unsigned → stays positive
        i = Integer(0x8000000000000000, 64, False)
        assert i.val == 0x8000000000000000

    def test_mask_to_width(self):
        # Value wider than width gets masked
        i = Integer(0x1FF, 8, False)
        assert i.val == 0xFF

    def test_x_value(self):
        i = Integer("X", 0, False)
        assert i.val == "X"

    def test_as_unsigned(self):
        i = Integer(0x80000000, 32, True)
        assert i.val == -2147483648
        assert i._as_unsigned() == 0x80000000

    def test_as_unsigned_positive(self):
        i = Integer(42, 32, False)
        assert i._as_unsigned() == 42


# --- Arithmetic ---

class TestIntegerArithmetic:
    def test_add(self):
        a = Integer(3, 32, False)
        b = Integer(5, 32, False)
        r = a + b
        assert r.val == 8

    def test_sub(self):
        a = Integer(10, 32, False)
        b = Integer(3, 32, False)
        r = a - b
        assert r.val == 7

    def test_mul(self):
        a = Integer(6, 32, False)
        b = Integer(7, 32, False)
        r = a * b
        assert r.val == 42

    def test_x_propagation(self):
        a = Integer("X", 0, False)
        b = Integer(5, 32, False)
        r = a + b
        assert r.val == "X"


# --- Unsigned floor division (Verilog rule) ---

class TestUnsignedFloorDiv:
    def test_both_unsigned(self):
        a = Integer(0x8000000000000000, 64, False)
        b = Integer(2, 32, False)
        r = a // b
        assert r.val == 0x4000000000000000

    def test_mixed_unsigned_wins(self):
        # unsigned op signed → unsigned division
        a = Integer(0x8000000000000000, 64, False)
        b = Integer(2, 32, True)
        r = a // b
        assert r.val == 0x4000000000000000

    def test_both_signed(self):
        a = Integer(-10, 32, True)
        b = Integer(3, 32, True)
        r = a // b
        assert r.val == -4  # Python floor division

    def test_zero_division_guard(self):
        a = Integer(42, 32, False)
        b = Integer(0, 32, False)
        r = a // b
        assert r.val == 0


# --- Unsigned modulo ---

class TestUnsignedMod:
    def test_unsigned_mod(self):
        a = Integer(0x8000000000000000, 64, False)
        b = Integer(3, 32, False)
        r = a % b
        assert r.val == 0x8000000000000000 % 3

    def test_signed_mod(self):
        a = Integer(-10, 32, True)
        b = Integer(3, 32, True)
        r = a % b
        assert r.val == -10 % 3

    def test_zero_mod_guard(self):
        a = Integer(42, 32, False)
        b = Integer(0, 32, False)
        r = a % b
        assert r.val == 0


# --- Unsigned comparisons (Verilog rule) ---

class TestUnsignedComparisons:
    def test_le_unsigned_bit63(self):
        # 0x8000000000000000 <= 0x7FFFFFFFFFFFFFFF → False (unsigned)
        a = Integer(0x8000000000000000, 64, False)
        b = Integer(0x7FFFFFFFFFFFFFFF, 64, False)
        r = a <= b
        assert int(r) == 0

    def test_le_signed_bit63(self):
        # -2^63 <= 2^63-1 → True (signed)
        a = Integer(0x8000000000000000, 64, True)
        b = Integer(0x7FFFFFFFFFFFFFFF, 64, True)
        r = a <= b
        assert int(r) == 1

    def test_le_mixed_unsigned_wins(self):
        # signed(-2^63) vs unsigned(0x3000...) → unsigned comparison
        a = Integer(0x8000000000000000, 64, True)  # val = -2^63
        b = Integer(0x3000000000000000, 64, False)  # val = 0x3000...
        r = a <= b
        # unsigned: 0x8000... <= 0x3000... → False
        assert int(r) == 0

    def test_lt_unsigned(self):
        a = Integer(0xFFFFFFFFFFFFFFFF, 64, False)
        b = Integer(1, 32, False)
        r = a < b
        assert int(r) == 0  # unsigned: max > 1

    def test_gt_unsigned(self):
        a = Integer(0x8000000000000000, 64, False)
        b = Integer(0x7FFFFFFFFFFFFFFF, 64, False)
        r = a > b
        assert int(r) == 1

    def test_ge_unsigned(self):
        a = Integer(0x8000000000000000, 64, False)
        b = Integer(0x8000000000000000, 64, False)
        r = a >= b
        assert int(r) == 1

    def test_eq_unaffected_by_sign(self):
        a = Integer(0x8000000000000000, 64, True)
        b = Integer(0x8000000000000000, 64, False)
        # eq compares val directly; signed val is -2^63, unsigned is 2^63
        # These are different Python ints, so eq returns 0
        r = a == b
        assert int(r) == 0

    def test_x_comparison(self):
        a = Integer("X", 0, False)
        b = Integer(1, 32, False)
        r = a < b
        assert r.val == "X"


# --- Unsigned right shift ---

class TestUnsignedRShift:
    def test_unsigned_rshift(self):
        # 0x8000000000000000 >> 63 → 1 (logical shift)
        a = Integer(0x8000000000000000, 64, False)
        b = Integer(63, 32, True)
        r = a >> b
        assert r.val == 1

    def test_signed_rshift(self):
        # -1 >> 1 → -1 (arithmetic shift, sign extension)
        a = Integer(0xFF, 8, True)  # val = -1
        b = Integer(1, 32, True)
        r = a >> b
        assert r.val == -1

    def test_mixed_unsigned_rshift(self):
        # Shift signedness follows left operand only (C semantics)
        # Left operand is signed -> arithmetic shift, regardless of rhs signedness
        a = Integer(0x8000000000000000, 64, True)  # val = -2^63
        b = Integer(63, 32, False)  # unsigned shift amount
        r = a >> b
        # Signed left operand: arithmetic shift -> -2^63 >> 63 = -1
        assert r.val == -1

    def test_unsigned_lhs_signed_rhs_rshift(self):
        # Left operand is unsigned -> logical shift, regardless of rhs signedness
        a = Integer(0x8000000000000000, 64, False)  # unsigned
        b = Integer(63, 32, True)  # signed shift amount
        r = a >> b
        # Unsigned left operand: logical shift -> 0x8000... >> 63 = 1
        assert r.val == 1


# --- visit_AHDL_CONST width ---

class TestConstWidth:
    def test_small_constant_width32(self):
        # Constants <= 32 bits should have width=32
        v = 42
        width = max(v.bit_length() + 1, 32)
        i = Integer(v, width, True)
        assert i.val == 42
        assert i.width == 32

    def test_large_constant_preserved(self):
        # 0x000FFFFFFFFFFFFF (52 bits) should NOT be truncated
        v = 0x000FFFFFFFFFFFFF
        width = max(v.bit_length() + 1, 32)
        i = Integer(v, width, True)
        assert i.val == v  # preserved, not truncated

    def test_mask64_preserved(self):
        v = 0xFFFFFFFFFFFFFFFF
        width = max(v.bit_length() + 1, 32)
        i = Integer(v, width, True)
        assert i.val == v

    def test_32bit_boundary(self):
        # 0x100000000 (33 bits) — just over 32 bits
        v = 0x100000000
        width = max(v.bit_length() + 1, 32)
        i = Integer(v, width, True)
        assert i.val == v

    def test_truncated_with_width32(self):
        # Verify the old bug: width=32 truncates large values
        v = 0x000FFFFFFFFFFFFF
        i = Integer(v, 32, True)
        # Masked to 32 bits then twos_comp → -1
        assert i.val == -1  # This is the bug we fixed


# --- op_is_unsigned ---

class TestOpIsUnsigned:
    def test_both_unsigned(self):
        a = Integer(1, 32, False)
        b = Integer(2, 32, False)
        assert Integer._op_is_unsigned(a, b) == True

    def test_both_signed(self):
        a = Integer(1, 32, True)
        b = Integer(2, 32, True)
        assert Integer._op_is_unsigned(a, b) == False

    def test_mixed(self):
        a = Integer(1, 32, False)
        b = Integer(2, 32, True)
        assert Integer._op_is_unsigned(a, b) == True


# --- Simulator context manager ---

class TestSimulatorContextManager:
    def test_enter_calls_begin(self):
        """__enter__ calls begin() and returns self."""
        sim = Simulator.__new__(Simulator)
        sim.begin = MagicMock()
        result = sim.__enter__()
        sim.begin.assert_called_once()
        assert result is sim

    def test_exit_calls_end(self):
        """__exit__ calls end()."""
        sim = Simulator.__new__(Simulator)
        sim.end = MagicMock()
        sim.__exit__(None, None, None)
        sim.end.assert_called_once()

    def test_exit_calls_end_on_exception(self):
        """__exit__ calls end() even when exception occurred."""
        sim = Simulator.__new__(Simulator)
        sim.end = MagicMock()
        sim.__exit__(ValueError, ValueError("test"), None)
        sim.end.assert_called_once()
