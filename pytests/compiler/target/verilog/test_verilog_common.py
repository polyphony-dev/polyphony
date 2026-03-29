"""Tests for verilog_common.py utility functions."""
from polyphony.compiler.target.verilog.verilog_common import (
    pyop2verilogop, is_verilog_keyword, PYTHON_OP_2_VERILOG_OP_MAP,
)


# ============================================================
# pyop2verilogop
# ============================================================

def test_pyop2verilogop_add():
    assert pyop2verilogop('Add') == '+'


def test_pyop2verilogop_sub():
    assert pyop2verilogop('Sub') == '-'


def test_pyop2verilogop_mult():
    assert pyop2verilogop('Mult') == '*'


def test_pyop2verilogop_floordiv():
    assert pyop2verilogop('FloorDiv') == '/'


def test_pyop2verilogop_mod():
    assert pyop2verilogop('Mod') == '%'


def test_pyop2verilogop_lshift():
    assert pyop2verilogop('LShift') == '<<'


def test_pyop2verilogop_rshift_signed():
    assert pyop2verilogop('RShift', signed=True) == '>>>'


def test_pyop2verilogop_rshift_unsigned():
    assert pyop2verilogop('RShift', signed=False) == '>>'


def test_pyop2verilogop_rshift_default_signed():
    assert pyop2verilogop('RShift') == '>>>'


def test_pyop2verilogop_bitor():
    assert pyop2verilogop('BitOr') == '|'


def test_pyop2verilogop_bitxor():
    assert pyop2verilogop('BitXor') == '^'


def test_pyop2verilogop_bitand():
    assert pyop2verilogop('BitAnd') == '&'


def test_pyop2verilogop_eq():
    assert pyop2verilogop('Eq') == '=='


def test_pyop2verilogop_noteq():
    assert pyop2verilogop('NotEq') == '!='


def test_pyop2verilogop_lt():
    assert pyop2verilogop('Lt') == '<'


def test_pyop2verilogop_lte():
    assert pyop2verilogop('LtE') == '<='


def test_pyop2verilogop_gt():
    assert pyop2verilogop('Gt') == '>'


def test_pyop2verilogop_gte():
    assert pyop2verilogop('GtE') == '>='


def test_pyop2verilogop_isnot():
    assert pyop2verilogop('IsNot') == '!='


def test_pyop2verilogop_and():
    assert pyop2verilogop('And') == '&&'


def test_pyop2verilogop_or():
    assert pyop2verilogop('Or') == '||'


def test_pyop2verilogop_usub():
    assert pyop2verilogop('USub') == '-'


def test_pyop2verilogop_uadd():
    assert pyop2verilogop('UAdd') == '+'


def test_pyop2verilogop_not():
    assert pyop2verilogop('Not') == '!'


def test_pyop2verilogop_invert():
    assert pyop2verilogop('Invert') == '~'


def test_pyop2verilogop_all_keys_covered():
    """All keys in the map are accessible via pyop2verilogop."""
    for op in PYTHON_OP_2_VERILOG_OP_MAP:
        result = pyop2verilogop(op)
        assert result == PYTHON_OP_2_VERILOG_OP_MAP[op]


# ============================================================
# is_verilog_keyword
# ============================================================

def test_is_verilog_keyword_module():
    assert is_verilog_keyword('module') is True


def test_is_verilog_keyword_wire():
    assert is_verilog_keyword('wire') is True


def test_is_verilog_keyword_reg():
    assert is_verilog_keyword('reg') is True


def test_is_verilog_keyword_always():
    assert is_verilog_keyword('always') is True


def test_is_verilog_keyword_begin():
    assert is_verilog_keyword('begin') is True


def test_is_verilog_keyword_end():
    assert is_verilog_keyword('end') is True


def test_is_verilog_keyword_if():
    assert is_verilog_keyword('if') is True


def test_is_verilog_keyword_case():
    assert is_verilog_keyword('case') is True


def test_is_verilog_keyword_not_keyword():
    assert is_verilog_keyword('my_signal') is False


def test_is_verilog_keyword_empty_string():
    assert is_verilog_keyword('') is False


def test_is_verilog_keyword_partial_match():
    """Partial keyword match is not a keyword."""
    assert is_verilog_keyword('mod') is False


def test_is_verilog_keyword_uppercase():
    """Keywords are lowercase — uppercase is not a keyword."""
    assert is_verilog_keyword('MODULE') is False
