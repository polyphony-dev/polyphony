"""Tests for AHDLSignalReplacer in ahdl/transformers/varreplacer.py.

Covers lines: 6, 9-13 (visit_AHDL_VAR logic and __init__).
"""
import pytest

from polyphony.compiler.ahdl.transformers.varreplacer import AHDLSignalReplacer
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_MOVE, AHDL_VAR, AHDL_CONST, AHDL_TRANSITION, State,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule, FSM
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

def build_scope():
    setup_test()
    src = "scope test():function\n  tags: \n"
    # Use a minimal valid IrReader source
    full_src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
'''
    parser = IrReader(full_src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl, scope


def make_module_with_move(hdl, codes):
    """Build an FSM with a single state containing the given codes."""
    state_sig = hdl.gen_sig('state_var', 4, {'reg'})
    scope = hdl.scope
    fsm = FSM('main_fsm', scope, state_sig)
    stg = STG('main', None, hdl)
    block = AHDL_BLOCK('S0', codes)
    state = stg.new_state('S0', block, 0)
    stg.add_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm
    return hdl, fsm, stg


# ============================================================
# Unit tests: visit_AHDL_VAR directly (no HDLModule)
# ============================================================

def test_visit_AHDL_VAR_replaced():
    """visit_AHDL_VAR returns a new AHDL_VAR when vars key is in replace_table."""
    hdl, scope = make_hdlmodule()
    sig_a = hdl.gen_sig('sig_a', 8, {'reg'})
    sig_b = hdl.gen_sig('sig_b', 8, {'reg'})

    # replace_table maps tuple-of-signals to tuple-of-signals
    replace_table = {(sig_a,): (sig_b,)}
    replacer = AHDLSignalReplacer(replace_table)

    ahdl = AHDL_VAR(sig_a, Ctx.LOAD)
    result = replacer.visit_AHDL_VAR(ahdl)

    assert isinstance(result, AHDL_VAR)
    assert result.vars == (sig_b,)
    assert result.ctx == Ctx.LOAD


def test_visit_AHDL_VAR_not_replaced():
    """visit_AHDL_VAR returns the original ahdl when vars key is not in replace_table."""
    hdl, scope = make_hdlmodule()
    sig_a = hdl.gen_sig('sig_a2', 8, {'reg'})
    sig_b = hdl.gen_sig('sig_b2', 8, {'reg'})
    sig_c = hdl.gen_sig('sig_c2', 8, {'reg'})

    # replace_table maps sig_b, but we look up sig_a
    replace_table = {(sig_b,): (sig_c,)}
    replacer = AHDLSignalReplacer(replace_table)

    ahdl = AHDL_VAR(sig_a, Ctx.LOAD)
    result = replacer.visit_AHDL_VAR(ahdl)

    assert result is ahdl


def test_visit_AHDL_VAR_store_ctx_replaced():
    """Replacement works regardless of context (STORE)."""
    hdl, scope = make_hdlmodule()
    sig_a = hdl.gen_sig('sig_store_a', 8, {'reg'})
    sig_b = hdl.gen_sig('sig_store_b', 8, {'reg'})

    replace_table = {(sig_a,): (sig_b,)}
    replacer = AHDLSignalReplacer(replace_table)

    ahdl = AHDL_VAR(sig_a, Ctx.STORE)
    result = replacer.visit_AHDL_VAR(ahdl)

    assert isinstance(result, AHDL_VAR)
    assert result.vars == (sig_b,)
    assert result.ctx == Ctx.STORE


def test_visit_AHDL_VAR_empty_replace_table():
    """With an empty replace_table every var is returned as-is."""
    hdl, scope = make_hdlmodule()
    sig = hdl.gen_sig('sig_empty', 8, {'reg'})

    replacer = AHDLSignalReplacer({})
    ahdl = AHDL_VAR(sig, Ctx.LOAD)
    result = replacer.visit_AHDL_VAR(ahdl)

    assert result is ahdl


# ============================================================
# Integration test: process() on a full HDLModule
# ============================================================

def test_process_replaces_in_fsm():
    """process() walks FSM states and replaces matching AHDL_VAR in src of AHDL_MOVE."""
    hdl, scope = make_hdlmodule()
    sig_src = hdl.gen_sig('fsm_src', 8, {'reg'})
    sig_dst = hdl.gen_sig('fsm_dst', 8, {'reg'})
    sig_new = hdl.gen_sig('fsm_new', 8, {'reg'})

    src_var = AHDL_VAR(sig_src, Ctx.LOAD)
    dst_var = AHDL_VAR(sig_dst, Ctx.STORE)
    move = AHDL_MOVE(dst_var, src_var)
    trans = AHDL_TRANSITION('')

    codes = (move, trans)
    hdl, fsm, stg = make_module_with_move(hdl, codes)

    # Replace sig_src with sig_new
    replace_table = {(sig_src,): (sig_new,)}
    replacer = AHDLSignalReplacer(replace_table)
    replacer.process(hdl)

    state = stg.get_state('S0')
    new_move = state.block.codes[0]
    assert isinstance(new_move, AHDL_MOVE)
    assert isinstance(new_move.src, AHDL_VAR)
    assert new_move.src.vars == (sig_new,)
    # dst was not in replace_table, remains sig_dst
    assert new_move.dst.vars == (sig_dst,)


def test_process_no_match_leaves_fsm_unchanged():
    """process() with a non-matching replace_table leaves AHDL_MOVE src unchanged."""
    hdl, scope = make_hdlmodule()
    sig_src = hdl.gen_sig('noop_src', 8, {'reg'})
    sig_dst = hdl.gen_sig('noop_dst', 8, {'reg'})
    sig_other = hdl.gen_sig('noop_other', 8, {'reg'})

    src_var = AHDL_VAR(sig_src, Ctx.LOAD)
    dst_var = AHDL_VAR(sig_dst, Ctx.STORE)
    move = AHDL_MOVE(dst_var, src_var)
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_move(hdl, (move, trans))

    replace_table = {(sig_other,): (sig_dst,)}
    replacer = AHDLSignalReplacer(replace_table)
    replacer.process(hdl)

    state = stg.get_state('S0')
    new_move = state.block.codes[0]
    assert isinstance(new_move, AHDL_MOVE)
    assert new_move.src.vars == (sig_src,)
