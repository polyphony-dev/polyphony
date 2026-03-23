"""Tests for BitWidthDetector covering all visit_* methods."""
import pytest

from polyphony.compiler.ahdl.analysis.bitwidthdetector import BitWidthDetector
from polyphony.compiler.ahdl.ahdl import (
    AHDL_CONCAT,
    AHDL_CONST,
    AHDL_FUNCALL,
    AHDL_IF_EXP,
    AHDL_MEMVAR,
    AHDL_OP,
    AHDL_SLICE,
    AHDL_SUBSCRIPT,
    AHDL_VAR,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

IR_SRC = """
scope test
tags function returnable
return int32

blk1:
ret @return
"""


def build_scope():
    setup_test()
    parser = IrReader(IR_SRC)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


# ============================================================
# Tests: visit_AHDL_CONST
# ============================================================

def test_const_int_returns_default_int_width():
    """visit_AHDL_CONST with an int value returns env.config.default_int_width."""
    make_hdlmodule()
    detector = BitWidthDetector()
    result = detector.visit(AHDL_CONST(42))
    assert result == env.config.default_int_width


def test_const_str_returns_zero():
    """visit_AHDL_CONST with a str value returns 0."""
    make_hdlmodule()
    detector = BitWidthDetector()
    result = detector.visit(AHDL_CONST("some_signal"))
    assert result == 0


# ============================================================
# Tests: visit_AHDL_OP
# ============================================================

def test_op_relop_returns_one():
    """visit_AHDL_OP with a relational operator returns 1."""
    make_hdlmodule()
    detector = BitWidthDetector()
    op = AHDL_OP('Eq', AHDL_CONST(1), AHDL_CONST(2))
    result = detector.visit(op)
    assert result == 1


def test_op_relop_lt_returns_one():
    """visit_AHDL_OP with Lt returns 1."""
    make_hdlmodule()
    detector = BitWidthDetector()
    op = AHDL_OP('Lt', AHDL_CONST(0), AHDL_CONST(1))
    result = detector.visit(op)
    assert result == 1


def test_op_non_relop_returns_max_of_arg_widths():
    """visit_AHDL_OP with Add returns the max width of its args."""
    hdl = make_hdlmodule()
    # sig with width 16 (no 'int' tag) → contributes 16
    # const contributes default_int_width (32)
    detector = BitWidthDetector()
    op = AHDL_OP('Add', AHDL_CONST(0), AHDL_CONST(0))
    # Both AHDL_CONST(int) → default_int_width each → max is default_int_width
    result = detector.visit(op)
    assert result == env.config.default_int_width


def test_op_non_relop_with_var_picks_max():
    """visit_AHDL_OP uses max over all arg widths for non-relops."""
    hdl = make_hdlmodule()
    sig8 = hdl.gen_sig('w8', 8, {'reg'})      # no 'int' tag → width = 8
    sig16 = hdl.gen_sig('w16', 16, {'reg'})   # no 'int' tag → width = 16
    detector = BitWidthDetector()
    op = AHDL_OP('Add', AHDL_VAR(sig8, Ctx.LOAD), AHDL_VAR(sig16, Ctx.LOAD))
    result = detector.visit(op)
    assert result == 16


# ============================================================
# Tests: visit_AHDL_VAR
# ============================================================

def test_var_with_int_tag_returns_width_minus_one():
    """visit_AHDL_VAR with 'int' tag returns sig.width - 1."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('int_var', 8, {'reg', 'int'})
    detector = BitWidthDetector()
    result = detector.visit(AHDL_VAR(sig, Ctx.LOAD))
    assert result == 7   # 8 - 1


def test_var_without_int_tag_returns_width():
    """visit_AHDL_VAR without 'int' tag returns sig.width."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('uint_var', 8, {'reg'})
    detector = BitWidthDetector()
    result = detector.visit(AHDL_VAR(sig, Ctx.LOAD))
    assert result == 8


def test_var_width_16_int_tag():
    """visit_AHDL_VAR with int tag and width 16 returns 15."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('int16_var', 16, {'reg', 'int'})
    detector = BitWidthDetector()
    result = detector.visit(AHDL_VAR(sig, Ctx.LOAD))
    assert result == 15


# ============================================================
# Tests: visit_AHDL_MEMVAR
# ============================================================

def test_memvar_without_int_tag_returns_first_element_of_width():
    """visit_AHDL_MEMVAR without 'int' tag returns width[0]."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('arr', (8, 4), {'regarray'})
    detector = BitWidthDetector()
    result = detector.visit(AHDL_MEMVAR(sig, Ctx.LOAD))
    assert result == 8


def test_memvar_with_int_tag_returns_first_element_minus_one():
    """visit_AHDL_MEMVAR with 'int' tag returns width[0] - 1."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('int_arr', (8, 4), {'regarray', 'int'})
    detector = BitWidthDetector()
    result = detector.visit(AHDL_MEMVAR(sig, Ctx.LOAD))
    assert result == 7


def test_memvar_16_element_width():
    """visit_AHDL_MEMVAR with tuple width (16, 8) and no int tag returns 16."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('arr16', (16, 8), {'regarray'})
    detector = BitWidthDetector()
    result = detector.visit(AHDL_MEMVAR(sig, Ctx.LOAD))
    assert result == 16


# ============================================================
# Tests: visit_AHDL_SUBSCRIPT
# ============================================================

def test_subscript_delegates_to_memvar():
    """visit_AHDL_SUBSCRIPT returns the result of visiting the memvar."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('sub_arr', (12, 4), {'regarray'})
    memvar = AHDL_MEMVAR(sig, Ctx.LOAD)
    subscript = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    detector = BitWidthDetector()
    result = detector.visit(subscript)
    assert result == 12   # width[0] with no 'int' tag


def test_subscript_with_int_memvar():
    """visit_AHDL_SUBSCRIPT with 'int' memvar returns width[0] - 1."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('sub_int_arr', (10, 2), {'regarray', 'int'})
    memvar = AHDL_MEMVAR(sig, Ctx.LOAD)
    subscript = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    detector = BitWidthDetector()
    result = detector.visit(subscript)
    assert result == 9   # 10 - 1


# ============================================================
# Tests: visit_AHDL_FUNCALL
# ============================================================

def test_funcall_delegates_to_name_var():
    """visit_AHDL_FUNCALL returns the width of the name var."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('fn_name', 20, {'reg'})
    name_var = AHDL_VAR(sig, Ctx.LOAD)
    funcall = AHDL_FUNCALL(name_var, ())
    detector = BitWidthDetector()
    result = detector.visit(funcall)
    assert result == 20  # no 'int' tag → width


def test_funcall_with_int_name_var():
    """visit_AHDL_FUNCALL with 'int' name var returns width - 1."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('fn_int', 16, {'reg', 'int'})
    name_var = AHDL_VAR(sig, Ctx.LOAD)
    funcall = AHDL_FUNCALL(name_var, (AHDL_CONST(1),))
    detector = BitWidthDetector()
    result = detector.visit(funcall)
    assert result == 15  # 16 - 1


# ============================================================
# Tests: visit_AHDL_IF_EXP
# ============================================================

def test_if_exp_returns_max_of_lexp_rexp():
    """visit_AHDL_IF_EXP returns max of lexp and rexp widths."""
    hdl = make_hdlmodule()
    sig8 = hdl.gen_sig('ifexp_l', 8, {'reg'})
    sig12 = hdl.gen_sig('ifexp_r', 12, {'reg'})
    cond = AHDL_CONST(1)
    lexp = AHDL_VAR(sig8, Ctx.LOAD)
    rexp = AHDL_VAR(sig12, Ctx.LOAD)
    if_exp = AHDL_IF_EXP(cond, lexp, rexp)
    detector = BitWidthDetector()
    result = detector.visit(if_exp)
    assert result == 12


def test_if_exp_equal_widths():
    """visit_AHDL_IF_EXP with equal-width branches returns that width."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('ife_a', 10, {'reg'})
    sig_b = hdl.gen_sig('ife_b', 10, {'reg'})
    if_exp = AHDL_IF_EXP(AHDL_CONST(0), AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_b, Ctx.LOAD))
    detector = BitWidthDetector()
    result = detector.visit(if_exp)
    assert result == 10


def test_if_exp_lexp_wider_than_rexp():
    """visit_AHDL_IF_EXP returns lexp width when lexp is wider."""
    hdl = make_hdlmodule()
    sig_l = hdl.gen_sig('ife_wide', 24, {'reg'})
    sig_r = hdl.gen_sig('ife_narrow', 4, {'reg'})
    if_exp = AHDL_IF_EXP(AHDL_CONST(1), AHDL_VAR(sig_l, Ctx.LOAD), AHDL_VAR(sig_r, Ctx.LOAD))
    detector = BitWidthDetector()
    result = detector.visit(if_exp)
    assert result == 24


# ============================================================
# Tests: visit() method — assert + None-return branch
# ============================================================

def test_visit_asserts_on_non_ahdl_exp():
    """visit() raises AssertionError when given a non-AHDL_EXP argument."""
    make_hdlmodule()
    detector = BitWidthDetector()
    with pytest.raises(AssertionError):
        detector.visit(object())  # type: ignore[arg-type]


def test_visit_raises_not_implemented_for_concat():
    """visit_AHDL_CONCAT raises NotImplementedError."""
    from polyphony.compiler.ahdl.ahdl import AHDL_CONCAT
    make_hdlmodule()
    detector = BitWidthDetector()
    concat = AHDL_CONCAT((), None)
    with pytest.raises(NotImplementedError):
        detector.visit(concat)


def test_visit_raises_not_implemented_for_slice():
    """visit_AHDL_SLICE raises NotImplementedError."""
    from polyphony.compiler.ahdl.ahdl import AHDL_SLICE
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('slc_sig', 8, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    slc = AHDL_SLICE(var, AHDL_CONST(7), AHDL_CONST(0))
    detector = BitWidthDetector()
    with pytest.raises(NotImplementedError):
        detector.visit(slc)
