"""Tests for AHDLRenameVisitor and NetRenamer in ahdl/transformers/netrenamer.py.

Covers uncovered lines: 29-31, 34-36, 39-52, 57-58, 61-70.
"""
import pytest

from polyphony.compiler.ahdl.transformers.netrenamer import AHDLRenameVisitor, NetRenamer
from polyphony.compiler.ahdl.ahdl import (
    AHDL_CONST, AHDL_OP, AHDL_VAR, AHDL_ASSIGN,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule
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


# ============================================================
# AHDLRenameVisitor — visit_AHDL_CONST
# ============================================================

def test_rename_const_positive_int():
    """visit_AHDL_CONST with positive int returns str(ahdl) == '5'."""
    visitor = AHDLRenameVisitor()
    result = visitor.visit_AHDL_CONST(AHDL_CONST(5))
    assert result == '5'


def test_rename_const_negative_int():
    """visit_AHDL_CONST with negative int returns 'minus_N'."""
    visitor = AHDLRenameVisitor()
    result = visitor.visit_AHDL_CONST(AHDL_CONST(-3))
    assert result == 'minus_3'


def test_rename_const_zero():
    """visit_AHDL_CONST with zero (non-negative int) returns '0'."""
    visitor = AHDLRenameVisitor()
    result = visitor.visit_AHDL_CONST(AHDL_CONST(0))
    assert result == '0'


# ============================================================
# AHDLRenameVisitor — visit_AHDL_VAR
# ============================================================

def test_rename_var_field_sig_returns_str():
    """visit_AHDL_VAR with field-tagged sig returns str(ahdl)."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('nr_field', 32, {'reg', 'field'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    visitor = AHDLRenameVisitor()
    result = visitor.visit_AHDL_VAR(var)
    assert result == str(var)
    assert result is not None


def test_rename_var_connector_sig_returns_str():
    """visit_AHDL_VAR with connector-tagged sig returns str(ahdl)."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('nr_conn', 32, {'reg', 'connector'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    visitor = AHDLRenameVisitor()
    result = visitor.visit_AHDL_VAR(var)
    assert result == str(var)
    assert result is not None


def test_rename_var_regular_sig_returns_none():
    """visit_AHDL_VAR with plain reg sig (no field/connector) returns None."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('nr_plain', 32, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    visitor = AHDLRenameVisitor()
    assert visitor.visit_AHDL_VAR(var) is None


# ============================================================
# AHDLRenameVisitor — visit_AHDL_OP (unary)
# ============================================================

def test_rename_op_unary_valid_arg():
    """visit_AHDL_OP unary with field sig arg → 'op_arg'."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('nr_unary_f', 32, {'reg', 'field'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    op = AHDL_OP('USub', var)
    visitor = AHDLRenameVisitor()
    result = visitor.visit_AHDL_OP(op)
    assert result == f'minus_{str(var)}'


def test_rename_op_unary_none_arg_returns_none():
    """visit_AHDL_OP unary with regular (non-field/connector) var returns None."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('nr_unary_r', 32, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    op = AHDL_OP('Not', var)
    visitor = AHDLRenameVisitor()
    assert visitor.visit_AHDL_OP(op) is None


# ============================================================
# AHDLRenameVisitor — visit_AHDL_OP (binary)
# ============================================================

def test_rename_op_binary_both_valid():
    """visit_AHDL_OP binary with two valid args returns 'arg0_op_arg1'."""
    visitor = AHDLRenameVisitor()
    # Both AHDL_CONST args produce non-None strings
    op = AHDL_OP('Add', AHDL_CONST(3), AHDL_CONST(4))
    result = visitor.visit_AHDL_OP(op)
    assert result == '3_add_4'


def test_rename_op_binary_arg0_none_returns_none():
    """visit_AHDL_OP binary returns None when arg0 visit returns None."""
    hdl = make_hdlmodule()
    # arg0 is a regular reg signal → visit_AHDL_VAR returns None
    sig = hdl.gen_sig('nr_bin_r0', 32, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    op = AHDL_OP('Add', var, AHDL_CONST(4))
    visitor = AHDLRenameVisitor()
    assert visitor.visit_AHDL_OP(op) is None


def test_rename_op_binary_arg1_none_returns_none():
    """visit_AHDL_OP binary returns None when arg1 visit returns None (arg0 valid)."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('nr_bin_r1', 32, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    # arg0 = AHDL_CONST (valid), arg1 = regular var (None)
    op = AHDL_OP('Sub', AHDL_CONST(10), var)
    visitor = AHDLRenameVisitor()
    assert visitor.visit_AHDL_OP(op) is None


def test_rename_op_more_than_two_args_returns_none():
    """visit_AHDL_OP with >2 args returns None (not unary or binary branch)."""
    # AHDL_OP supports varargs, so construct one with 3 args
    op = AHDL_OP('Add', AHDL_CONST(1), AHDL_CONST(2), AHDL_CONST(3))
    visitor = AHDLRenameVisitor()
    assert visitor.visit_AHDL_OP(op) is None


# ============================================================
# NetRenamer — process()
# ============================================================

def test_netrenamer_no_assigns_noop():
    """NetRenamer.process with no AHDL_ASSIGN decls does nothing."""
    hdl = make_hdlmodule()
    # no decls added → get_static_assignment returns []
    renamer = NetRenamer()
    renamer.process(hdl)  # must not raise


def test_netrenamer_const_src_assign_skipped():
    """NetRenamer skips AHDL_ASSIGN where src is AHDL_CONST (no rename)."""
    hdl = make_hdlmodule()
    sig_dst = hdl.gen_sig('nr_csa_dst', 32, {'net'})
    assign = AHDL_ASSIGN(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_CONST(0))
    hdl.add_decl(assign)

    original_name = sig_dst.name
    NetRenamer().process(hdl)
    # Name must be unchanged (AHDL_CONST src is skipped)
    assert sig_dst.name == original_name


def test_netrenamer_var_src_assign_skipped():
    """NetRenamer skips AHDL_ASSIGN where src is AHDL_VAR (no rename)."""
    hdl = make_hdlmodule()
    sig_src = hdl.gen_sig('nr_vsa_src', 32, {'reg'})
    sig_dst = hdl.gen_sig('nr_vsa_dst', 32, {'net'})
    assign = AHDL_ASSIGN(
        AHDL_VAR(sig_dst, Ctx.STORE),
        AHDL_VAR(sig_src, Ctx.LOAD),
    )
    hdl.add_decl(assign)

    original_name = sig_dst.name
    NetRenamer().process(hdl)
    assert sig_dst.name == original_name


def test_netrenamer_op_renamer_returns_none_skipped():
    """NetRenamer skips when AHDLRenameVisitor returns None for the src."""
    hdl = make_hdlmodule()
    # Use a regular (non-field/connector) var as arg → visit_AHDL_VAR returns None
    sig_plain = hdl.gen_sig('nr_opnone_plain', 32, {'reg'})
    sig_dst = hdl.gen_sig('nr_opnone_dst', 32, {'net'})
    # AHDL_OP with a single plain-var arg → unary → s_arg = None → returns None
    op = AHDL_OP('USub', AHDL_VAR(sig_plain, Ctx.LOAD))
    assign = AHDL_ASSIGN(AHDL_VAR(sig_dst, Ctx.STORE), op)
    hdl.add_decl(assign)

    original_name = sig_dst.name
    NetRenamer().process(hdl)
    assert sig_dst.name == original_name


def test_netrenamer_op_src_renames_dst():
    """NetRenamer renames dst.sig.name when AHDLRenameVisitor returns a valid name."""
    hdl = make_hdlmodule()
    sig_dst = hdl.gen_sig('nr_rename_dst', 32, {'net'})
    # AHDL_OP(Add, AHDL_CONST(3), AHDL_CONST(4)) → renamer returns '3_add_4'
    op = AHDL_OP('Add', AHDL_CONST(3), AHDL_CONST(4))
    assign = AHDL_ASSIGN(AHDL_VAR(sig_dst, Ctx.STORE), op)
    hdl.add_decl(assign)

    NetRenamer().process(hdl)
    assert sig_dst.name == '3_add_4'


def test_netrenamer_op_src_replaces_dots_in_name():
    """NetRenamer replaces '.' with '_' in the renamed signal name."""
    hdl = make_hdlmodule()
    # Use field sig so str(var) is 'scope.field_name' containing a dot
    sig_field = hdl.gen_sig('nr.dot.field', 32, {'reg', 'field'})
    sig_dst = hdl.gen_sig('nr_dot_dst', 32, {'net'})
    # Unary op with field var → renamer returns e.g. 'not_nr.dot.field'
    op = AHDL_OP('Not', AHDL_VAR(sig_field, Ctx.LOAD))
    assign = AHDL_ASSIGN(AHDL_VAR(sig_dst, Ctx.STORE), op)
    hdl.add_decl(assign)

    NetRenamer().process(hdl)
    # Dots must be replaced with underscores
    assert '.' not in sig_dst.name
