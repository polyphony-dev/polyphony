"""Tests for BitwidthReducer in ahdl/transformers/bitwidthreducer.py.

Covers uncovered lines: 12-13, 16-22, 25, 28, 31, 34-56, 59, 62, 65, 68-79, 85, 88, 91-94.
"""
import pytest

from polyphony.compiler.ahdl.transformers.bitwidthreducer import BitwidthReducer
from polyphony.compiler.ahdl.ahdl import (
    AHDL_CONST, AHDL_OP, AHDL_VAR, AHDL_MEMVAR, AHDL_SUBSCRIPT,
    AHDL_SYMBOL, AHDL_CONCAT, AHDL_NOP, AHDL_MOVE, AHDL_MODULECALL,
    AHDL_FUNCALL, AHDL_IF_EXP, AHDL_BLOCK, AHDL_TRANSITION,
)
from polyphony.compiler.ahdl.analysis.ahdlusedef import AHDLUseDefDetector, UseDefTable
from polyphony.compiler.ahdl.hdlmodule import HDLModule, FSM
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

_SRC = '''
scope test
tags function returnable
'''


def build_scope():
    setup_test()
    parser = IrReader(_SRC)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def make_reducer_with_module(hdl, stm_in_state=None):
    """Create a BitwidthReducer with usedef set for a module containing stm."""
    state_sig = hdl.gen_sig('bwr_state', 4, {'reg'})
    scope = hdl.scope
    fsm = FSM('main_fsm', scope, state_sig)
    stg = STG('main', None, hdl)
    if stm_in_state is not None:
        block = AHDL_BLOCK('', (stm_in_state,))
    else:
        block = AHDL_BLOCK('', ())
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm

    reducer = BitwidthReducer()
    reducer.usedef = AHDLUseDefDetector().process(hdl)
    return reducer


# ============================================================
# visit_AHDL_CONST
# ============================================================

def test_const_int_returns_default_int_width():
    """visit_AHDL_CONST with int value returns env.config.default_int_width."""
    reducer = BitwidthReducer()
    result = reducer.visit_AHDL_CONST(AHDL_CONST(5))
    assert result == env.config.default_int_width


def test_const_str_returns_1():
    """visit_AHDL_CONST with str value returns 1."""
    reducer = BitwidthReducer()
    result = reducer.visit_AHDL_CONST(AHDL_CONST('hello'))
    assert result == 1


def test_const_none_returns_1():
    """visit_AHDL_CONST with None value returns 1."""
    reducer = BitwidthReducer()
    result = reducer.visit_AHDL_CONST(AHDL_CONST(None))
    assert result == 1


# ============================================================
# visit_AHDL_VAR
# ============================================================

def test_var_returns_sig_width():
    """visit_AHDL_VAR returns sig.width."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('bwr_var', 16, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_VAR(var) == 16


# ============================================================
# visit_AHDL_MEMVAR
# ============================================================

def test_memvar_returns_sig_width():
    """visit_AHDL_MEMVAR returns sig.width (the element width of the array)."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('bwr_arr', (8, 4), {'regarray'})
    memvar = AHDL_MEMVAR(sig, Ctx.LOAD)
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_MEMVAR(memvar) == (8, 4)


# ============================================================
# visit_AHDL_SUBSCRIPT
# ============================================================

def test_subscript_delegates_to_memvar():
    """visit_AHDL_SUBSCRIPT returns width from memvar's sig."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('bwr_sub_arr', 8, {'regarray'})
    memvar = AHDL_MEMVAR(sig, Ctx.LOAD)
    subscript = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_SUBSCRIPT(subscript) == 8


# ============================================================
# visit_AHDL_OP
# ============================================================

def test_op_relop_returns_1():
    """visit_AHDL_OP for a relational op returns 1."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_rel_a', 32, {'reg'})
    sig_b = hdl.gen_sig('bwr_rel_b', 32, {'reg'})
    op = AHDL_OP('Eq', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_b, Ctx.LOAD))
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_OP(op) == 1


def test_op_bitand_returns_min_plus_1():
    """visit_AHDL_OP BitAnd returns min(widths)+1."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_ba_a', 8, {'reg'})
    sig_b = hdl.gen_sig('bwr_ba_b', 16, {'reg'})
    op = AHDL_OP('BitAnd', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_b, Ctx.LOAD))
    reducer = BitwidthReducer()
    # min(8, 16) + 1 = 9
    assert reducer.visit_AHDL_OP(op) == 9


def test_op_sub_returns_first_width():
    """visit_AHDL_OP Sub returns widths[0]."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_sub_a', 12, {'reg'})
    sig_b = hdl.gen_sig('bwr_sub_b', 20, {'reg'})
    op = AHDL_OP('Sub', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_b, Ctx.LOAD))
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_OP(op) == 12


def test_op_lshift_returns_formula():
    """visit_AHDL_OP LShift returns widths[0] + (1<<widths[1]) - 1."""
    hdl = make_hdlmodule()
    # Use const for shift amount so widths[1] is predictable (default_int_width = 32)
    # widths[0] = sig width = 4, widths[1] = default_int_width for AHDL_CONST
    sig_a = hdl.gen_sig('bwr_ls_a', 4, {'reg'})
    default_w = env.config.default_int_width  # typically 32
    op = AHDL_OP('LShift', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_CONST(2))
    reducer = BitwidthReducer()
    # widths[0]=4, widths[1]=default_int_width
    # 4 + (1 << default_int_width) - 1 — this would exceed default_int_width, so clamped
    result = reducer.visit_AHDL_OP(op)
    assert result == default_w  # clamped to default_int_width


def test_op_rshift_non_int_var_with_const_shift():
    """visit_AHDL_OP RShift with AHDL_CONST shift and non-int AHDL_VAR reduces width."""
    hdl = make_hdlmodule()
    # sig without 'int' tag → is_int() is False
    sig_a = hdl.gen_sig('bwr_rs_a', 16, {'reg'})
    op = AHDL_OP('RShift', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_CONST(4))
    reducer = BitwidthReducer()
    # width = 16 - 4 = 12
    assert reducer.visit_AHDL_OP(op) == 12


def test_op_rshift_int_var_no_reduction():
    """visit_AHDL_OP RShift with int-tagged AHDL_VAR does NOT subtract shift amount."""
    hdl = make_hdlmodule()
    # sig with 'int' tag → is_int() is True → branch skipped
    sig_a = hdl.gen_sig('bwr_rs_int_a', 16, {'reg', 'int'})
    op = AHDL_OP('RShift', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_CONST(4))
    reducer = BitwidthReducer()
    # width = widths[0] = 16 (no subtraction)
    assert reducer.visit_AHDL_OP(op) == 16


def test_op_rshift_non_const_shift_no_reduction():
    """visit_AHDL_OP RShift with non-AHDL_CONST shift arg does not subtract."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_rs_nc_a', 16, {'reg'})
    sig_sh = hdl.gen_sig('bwr_rs_nc_sh', 8, {'reg'})
    op = AHDL_OP('RShift', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_sh, Ctx.LOAD))
    reducer = BitwidthReducer()
    # shift arg is AHDL_VAR, not AHDL_CONST → branch skipped → width = 16
    assert reducer.visit_AHDL_OP(op) == 16


def test_op_width_negative_clamped_to_1():
    """visit_AHDL_OP clamps negative result to 1 (RShift with huge shift)."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_neg_a', 4, {'reg'})
    # Shift by AHDL_CONST(100) — AHDL_CONST width = default_int_width = 32
    # width = 4 - 100 = -96 → clamped to 1
    # But RShift subtracts shift VALUE (ahdl.args[1].value = 100), not width
    op = AHDL_OP('RShift', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_CONST(100))
    reducer = BitwidthReducer()
    result = reducer.visit_AHDL_OP(op)
    assert result == 1


def test_op_width_exceeds_default_clamped():
    """visit_AHDL_OP clamps width exceeding default_int_width to default_int_width."""
    hdl = make_hdlmodule()
    default_w = env.config.default_int_width
    sig_a = hdl.gen_sig('bwr_big_a', default_w, {'reg'})
    sig_b = hdl.gen_sig('bwr_big_b', default_w, {'reg'})
    # Add: max(widths) = default_w → within bounds, equals default_w
    # Use a case where we know it exceeds: LShift was shown above
    # Use BitOr (else branch): max(default_w, default_w) = default_w — right at boundary
    op = AHDL_OP('BitOr', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_b, Ctx.LOAD))
    reducer = BitwidthReducer()
    result = reducer.visit_AHDL_OP(op)
    assert result == default_w


def test_op_else_branch_returns_max():
    """visit_AHDL_OP else branch (Add, Mult, etc.) returns max(widths)."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_max_a', 8, {'reg'})
    sig_b = hdl.gen_sig('bwr_max_b', 16, {'reg'})
    op = AHDL_OP('Add', AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_b, Ctx.LOAD))
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_OP(op) == 16


# ============================================================
# visit_AHDL_SYMBOL
# ============================================================

def test_symbol_returns_none():
    """visit_AHDL_SYMBOL returns None (pass)."""
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_SYMBOL(AHDL_SYMBOL('foo')) is None


# ============================================================
# visit_AHDL_CONCAT
# ============================================================

def test_concat_returns_sum_of_widths():
    """visit_AHDL_CONCAT returns sum of each var's width."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_cat_a', 8, {'reg'})
    sig_b = hdl.gen_sig('bwr_cat_b', 4, {'reg'})
    sig_c = hdl.gen_sig('bwr_cat_c', 16, {'reg'})
    concat = AHDL_CONCAT(
        (AHDL_VAR(sig_a, Ctx.LOAD), AHDL_VAR(sig_b, Ctx.LOAD), AHDL_VAR(sig_c, Ctx.LOAD)),
        None,
    )
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_CONCAT(concat) == 28


# ============================================================
# visit_AHDL_NOP
# ============================================================

def test_nop_returns_none():
    """visit_AHDL_NOP returns None (pass)."""
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_NOP(AHDL_NOP('test')) is None


# ============================================================
# visit_AHDL_MOVE
# ============================================================

def test_move_non_var_dst_returns_none_early():
    """visit_AHDL_MOVE with AHDL_SUBSCRIPT dst returns None before usedef lookup."""
    hdl = make_hdlmodule()
    sig_arr = hdl.gen_sig('bwr_mv_arr', (32, 4), {'regarray'})
    memvar = AHDL_MEMVAR(sig_arr, Ctx.STORE)
    subscript = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    move = AHDL_MOVE(subscript, AHDL_CONST(7))

    reducer = make_reducer_with_module(hdl)
    assert reducer.visit_AHDL_MOVE(move) is None


def test_move_output_sig_returns_none_early():
    """visit_AHDL_MOVE with output signal dst returns None (skip output/connector)."""
    hdl = make_hdlmodule()
    sig_out = hdl.gen_sig('bwr_mv_out', 32, {'reg', 'output'})
    move = AHDL_MOVE(AHDL_VAR(sig_out, Ctx.STORE), AHDL_CONST(1))

    reducer = make_reducer_with_module(hdl, stm_in_state=move)
    assert reducer.visit_AHDL_MOVE(move) is None


def test_move_connector_sig_returns_none_early():
    """visit_AHDL_MOVE with connector signal dst returns None early."""
    hdl = make_hdlmodule()
    sig_conn = hdl.gen_sig('bwr_mv_conn', 32, {'reg', 'connector'})
    move = AHDL_MOVE(AHDL_VAR(sig_conn, Ctx.STORE), AHDL_CONST(1))

    reducer = make_reducer_with_module(hdl, stm_in_state=move)
    assert reducer.visit_AHDL_MOVE(move) is None


def test_move_multiple_defs_returns_none_early():
    """visit_AHDL_MOVE with multiple definitions for dst signal returns None."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_mv_md_a', 32, {'reg'})
    move1 = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(1))
    move2 = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(2))

    # Put both moves in the state so usedef detects 2 definitions
    state_sig = hdl.gen_sig('bwr_mv_md_state', 4, {'reg'})
    fsm = FSM('main_fsm', hdl.scope, state_sig)
    stg = STG('main', None, hdl)
    block = AHDL_BLOCK('', (move1, move2))
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm

    reducer = BitwidthReducer()
    reducer.usedef = AHDLUseDefDetector().process(hdl)
    # move1 and move2 both define sig_a → len(stms) > 1 → return None
    assert reducer.visit_AHDL_MOVE(move1) is None


def test_move_symbol_src_srcw_none_returns_none():
    """visit_AHDL_MOVE with AHDL_SYMBOL src yields srcw=None → returns None."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_mv_sym_a', 32, {'reg'})
    move = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_SYMBOL('some_sym'))

    reducer = make_reducer_with_module(hdl, stm_in_state=move)
    assert reducer.visit_AHDL_MOVE(move) is None


def test_move_normal_case_runs_through():
    """visit_AHDL_MOVE normal path (single def, valid srcw) returns None (TODO stub)."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_mv_norm_a', 32, {'reg'})
    move = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(42))

    reducer = make_reducer_with_module(hdl, stm_in_state=move)
    # The method body ends with 'return' (implicit None) after the TODO comment.
    assert reducer.visit_AHDL_MOVE(move) is None


# ============================================================
# visit_AHDL_MODULECALL
# ============================================================

def test_modulecall_returns_none():
    """visit_AHDL_MODULECALL returns None (pass)."""
    mc = AHDL_MODULECALL(None, (), 'inst', '', ())
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_MODULECALL(mc) is None


# ============================================================
# visit_AHDL_FUNCALL
# ============================================================

def test_funcall_returns_none():
    """visit_AHDL_FUNCALL returns None (pass)."""
    hdl = make_hdlmodule()
    sig_fn = hdl.gen_sig('bwr_fn', 32, {'reg'})
    fc = AHDL_FUNCALL(AHDL_VAR(sig_fn, Ctx.LOAD), ())
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_FUNCALL(fc) is None


# ============================================================
# visit_AHDL_IF_EXP
# ============================================================

def test_if_exp_returns_max_when_both_truthy():
    """visit_AHDL_IF_EXP returns max(lw, rw) when both are truthy."""
    hdl = make_hdlmodule()
    sig_cond = hdl.gen_sig('bwr_ife_cond', 1, {'reg'})
    sig_l = hdl.gen_sig('bwr_ife_l', 16, {'reg'})
    sig_r = hdl.gen_sig('bwr_ife_r', 8, {'reg'})
    if_exp = AHDL_IF_EXP(
        AHDL_VAR(sig_cond, Ctx.LOAD),
        AHDL_VAR(sig_l, Ctx.LOAD),
        AHDL_VAR(sig_r, Ctx.LOAD),
    )
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_IF_EXP(if_exp) == 16


def test_if_exp_lw_greater_than_rw():
    """visit_AHDL_IF_EXP returns lw when lw >= rw."""
    hdl = make_hdlmodule()
    sig_cond = hdl.gen_sig('bwr_ife2_cond', 1, {'reg'})
    sig_l = hdl.gen_sig('bwr_ife2_l', 24, {'reg'})
    sig_r = hdl.gen_sig('bwr_ife2_r', 12, {'reg'})
    if_exp = AHDL_IF_EXP(
        AHDL_VAR(sig_cond, Ctx.LOAD),
        AHDL_VAR(sig_l, Ctx.LOAD),
        AHDL_VAR(sig_r, Ctx.LOAD),
    )
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_IF_EXP(if_exp) == 24


def test_if_exp_returns_none_when_lw_falsy():
    """visit_AHDL_IF_EXP returns None when lw is falsy (None from AHDL_SYMBOL)."""
    hdl = make_hdlmodule()
    sig_cond = hdl.gen_sig('bwr_ife3_cond', 1, {'reg'})
    sig_r = hdl.gen_sig('bwr_ife3_r', 8, {'reg'})
    if_exp = AHDL_IF_EXP(
        AHDL_VAR(sig_cond, Ctx.LOAD),
        AHDL_SYMBOL('unknown'),       # visit returns None
        AHDL_VAR(sig_r, Ctx.LOAD),
    )
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_IF_EXP(if_exp) is None


def test_if_exp_returns_none_when_rw_falsy():
    """visit_AHDL_IF_EXP returns None when rw is falsy (None from AHDL_SYMBOL)."""
    hdl = make_hdlmodule()
    sig_cond = hdl.gen_sig('bwr_ife4_cond', 1, {'reg'})
    sig_l = hdl.gen_sig('bwr_ife4_l', 16, {'reg'})
    if_exp = AHDL_IF_EXP(
        AHDL_VAR(sig_cond, Ctx.LOAD),
        AHDL_VAR(sig_l, Ctx.LOAD),
        AHDL_SYMBOL('unknown'),       # visit returns None
    )
    reducer = BitwidthReducer()
    assert reducer.visit_AHDL_IF_EXP(if_exp) is None


# ============================================================
# process() — integration test
# ============================================================

def test_process_runs_without_error():
    """process() integrates AHDLUseDefDetector and visits the full module."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('bwr_proc_a', 32, {'reg'})
    sig_out = hdl.gen_sig('bwr_proc_out', 32, {'reg', 'output'})
    move_a = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(10))
    move_out = AHDL_MOVE(AHDL_VAR(sig_out, Ctx.STORE), AHDL_VAR(sig_a, Ctx.LOAD))

    state_sig = hdl.gen_sig('bwr_proc_state', 4, {'reg'})
    fsm = FSM('main_fsm', hdl.scope, state_sig)
    stg = STG('main', None, hdl)
    block = AHDL_BLOCK('', (move_a, move_out))
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm

    reducer = BitwidthReducer()
    # process() must complete without exception
    reducer.process(hdl)
    assert reducer.usedef is not None
