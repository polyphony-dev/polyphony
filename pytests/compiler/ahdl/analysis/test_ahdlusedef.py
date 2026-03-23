"""Tests for UseDefTable and AHDLUseDefDetector in ahdlusedef.py."""
import pytest

from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK,
    AHDL_CONST,
    AHDL_MOVE,
    AHDL_NOP,
    AHDL_SEQ,
    AHDL_VAR,
)
from polyphony.compiler.ahdl.analysis.ahdlusedef import AHDLUseDefDetector, UseDefTable
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
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


def build_scope(src=IR_SRC):
    """Build a scope from IR source text."""
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule(scope):
    """Create a minimal HDLModule registered in env."""
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def make_signal(hdlscope, name, width=1, tags=None):
    """Create a signal via hdlscope.gen_sig."""
    if tags is None:
        tags = {'reg'}
    return hdlscope.gen_sig(name, width, tags)


def make_stg_with_state(hdlmodule, block, stg_name='main', state_name='S0'):
    """Create a STG with a single state containing the given block."""
    stg = STG(stg_name, None, hdlmodule)
    state = stg.new_state(state_name, block, 0)
    stg.set_states([state])
    return stg, state


def make_hdlmodule_with_fsm(stm):
    """
    Build an HDLModule with one FSM containing a state with the given statement.

    Returns (hdl, stg, state).
    """
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    block = AHDL_BLOCK('blk', (stm,))
    stg, state = make_stg_with_state(hdl, block)
    hdl.add_fsm('main_fsm', scope)
    hdl.add_fsm_stg('main_fsm', [stg])
    return hdl, stg, state


# ============================================================
# UseDefTable — add_sig_def / get_def_stms / get_sigs_defined_at
# ============================================================

def test_add_sig_def_and_get_def_stms():
    """add_sig_def registers sig→stm in the def table."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'x')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_def(sig, stm)
    assert stm in table.get_def_stms(sig)


def test_add_sig_def_and_get_sigs_defined_at():
    """add_sig_def registers stm→sig in the inverse def table."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'y')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_def(sig, stm)
    assert sig in table.get_sigs_defined_at(stm)


def test_add_sig_def_multiple_sigs_same_stm():
    """Multiple signals can be recorded as defined at the same statement."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_a = make_signal(hdl, 'a')
    sig_b = make_signal(hdl, 'b')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_def(sig_a, stm)
    table.add_sig_def(sig_b, stm)
    defined = table.get_sigs_defined_at(stm)
    assert sig_a in defined
    assert sig_b in defined


# ============================================================
# UseDefTable — remove_sig_def
# ============================================================

def test_remove_sig_def_removes_from_both_dicts():
    """remove_sig_def removes sig from both forward and inverse def tables."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'rem_def')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_def(sig, stm)
    table.remove_sig_def(sig, stm)
    assert stm not in table.get_def_stms(sig)
    assert sig not in table.get_sigs_defined_at(stm)


def test_remove_sig_def_nonexistent_is_noop():
    """remove_sig_def on a sig/stm that was never added does not raise."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'ghost_def')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.remove_sig_def(sig, stm)  # must not raise


# ============================================================
# UseDefTable — add_sig_use / get_use_stms / get_sigs_used_at
# ============================================================

def test_add_sig_use_and_get_use_stms():
    """add_sig_use registers sig→stm in the use table."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'u')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_use(sig, stm)
    assert stm in table.get_use_stms(sig)


def test_add_sig_use_and_get_sigs_used_at():
    """add_sig_use registers stm→sig in the inverse use table."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'v')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_use(sig, stm)
    assert sig in table.get_sigs_used_at(stm)


# ============================================================
# UseDefTable — add_sig_use_var / get_use_vars
# ============================================================

def test_add_sig_use_var_and_get_use_vars():
    """add_sig_use_var registers sig→var in the var-level use table."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'w')
    var = AHDL_VAR(sig, Ctx.LOAD)
    table = UseDefTable()
    table.add_sig_use_var(sig, var)
    assert var in table.get_use_vars(sig)


# ============================================================
# UseDefTable — remove_sig_use
# ============================================================

def test_remove_sig_use_removes_from_both_dicts():
    """remove_sig_use removes sig from both forward and inverse use tables."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'rem_use')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_use(sig, stm)
    table.remove_sig_use(sig, stm)
    assert stm not in table.get_use_stms(sig)
    assert sig not in table.get_sigs_used_at(stm)


def test_remove_sig_use_nonexistent_is_noop():
    """remove_sig_use on a sig/stm never added does not raise."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'ghost_use')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.remove_sig_use(sig, stm)  # must not raise


# ============================================================
# UseDefTable — remove_stm
# ============================================================

def test_remove_stm_clears_use_and_def():
    """remove_stm removes all uses and defs recorded for that statement."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_def = make_signal(hdl, 'def_sig')
    sig_use = make_signal(hdl, 'use_sig')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_def(sig_def, stm)
    table.add_sig_use(sig_use, stm)
    table.remove_stm(stm)
    assert stm not in table.get_def_stms(sig_def)
    assert stm not in table.get_use_stms(sig_use)
    assert sig_def not in table.get_sigs_defined_at(stm)
    assert sig_use not in table.get_sigs_used_at(stm)


# ============================================================
# UseDefTable — get_all_def_sigs
# ============================================================

def test_get_all_def_sigs_returns_all_defined_signals():
    """get_all_def_sigs returns the keys of the def sig→stm dict."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_a = make_signal(hdl, 'all_a')
    sig_b = make_signal(hdl, 'all_b')
    stm = AHDL_NOP('stm')
    table = UseDefTable()
    table.add_sig_def(sig_a, stm)
    table.add_sig_def(sig_b, stm)
    all_sigs = set(table.get_all_def_sigs())
    assert sig_a in all_sigs
    assert sig_b in all_sigs


def test_get_all_def_sigs_empty_when_no_defs():
    """get_all_def_sigs returns an empty view when no defs have been added."""
    table = UseDefTable()
    assert len(list(table.get_all_def_sigs())) == 0


# ============================================================
# UseDefTable — __str__
# ============================================================

def test_str_includes_sig_names_and_sections():
    """__str__ contains signal name, 'defs', 'uses' headers and stm repr."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    # Use alphabetically ordered names so sorting is predictable.
    sig_a = make_signal(hdl, 'aaa')
    sig_b = make_signal(hdl, 'bbb')
    stm_def = AHDL_NOP('def_stm')
    stm_use = AHDL_NOP('use_stm')
    table = UseDefTable()
    table.add_sig_def(sig_a, stm_def)
    table.add_sig_use(sig_b, stm_use)
    s = str(table)
    assert 'defs' in s
    assert 'uses' in s
    # sig_a appears under the sorted key list
    assert 'aaa' in s
    assert 'bbb' in s


def test_str_with_both_def_and_use_for_same_signal():
    """__str__ shows stm under both defs and uses when sig is both def and used."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig = make_signal(hdl, 'ccc')
    stm1 = AHDL_NOP('def')
    stm2 = AHDL_NOP('use')
    table = UseDefTable()
    table.add_sig_def(sig, stm1)
    table.add_sig_use(sig, stm2)
    s = str(table)
    assert "nop('def')" in s
    assert "nop('use')" in s


def test_str_empty_table_returns_empty_string():
    """__str__ on an empty UseDefTable returns an empty string."""
    table = UseDefTable()
    assert str(table) == ''


# ============================================================
# AHDLUseDefDetector — process
# ============================================================

def test_detector_process_returns_usedef_table():
    """process() returns a UseDefTable instance."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    block = AHDL_BLOCK('blk', (AHDL_NOP('n'),))
    stg, _ = make_stg_with_state(hdl, block)
    hdl.add_fsm('fsm0', scope)
    hdl.add_fsm_stg('fsm0', [stg])

    detector = AHDLUseDefDetector()
    table = detector.process(hdl)
    assert isinstance(table, UseDefTable)


# ============================================================
# AHDLUseDefDetector — visit_AHDL_VAR: STORE case
# ============================================================

def test_detector_records_def_for_store_var():
    """AHDL_VAR with STORE context is recorded as a def in the table."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_dst = make_signal(hdl, 'dst', tags={'reg'})
    stm = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_CONST(0))
    hdl_m, stg, state = make_hdlmodule_with_fsm(stm)
    # Re-use the hdl already built
    detector = AHDLUseDefDetector()
    table = detector.process(hdl_m)
    assert stm in table.get_def_stms(sig_dst)


# ============================================================
# AHDLUseDefDetector — visit_AHDL_VAR: LOAD case
# ============================================================

def test_detector_records_use_for_load_var():
    """AHDL_VAR with LOAD context is recorded as a use in the table."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_dst = make_signal(hdl, 'ldst', tags={'reg'})
    sig_src = make_signal(hdl, 'lsrc', tags={'reg'})
    stm = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_VAR(sig_src, Ctx.LOAD))
    hdl_m, stg, state = make_hdlmodule_with_fsm(stm)
    detector = AHDLUseDefDetector()
    table = detector.process(hdl_m)
    assert stm in table.get_use_stms(sig_src)


# ============================================================
# AHDLUseDefDetector — visit_AHDL_VAR: non-local var (len(vars) > 1)
# ============================================================

def test_detector_ignores_non_local_var():
    """AHDL_VAR with more than one signal in vars is not recorded."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig1 = make_signal(hdl, 'outer', tags={'reg'})
    sig2 = make_signal(hdl, 'inner', tags={'reg'})
    # Build a non-local AHDL_VAR: pass tuple of two signals
    non_local_src = AHDL_VAR((sig1, sig2), Ctx.LOAD)
    sig_dst = make_signal(hdl, 'nl_dst', tags={'reg'})
    stm = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), non_local_src)
    hdl_m, stg, state = make_hdlmodule_with_fsm(stm)
    detector = AHDLUseDefDetector()
    table = detector.process(hdl_m)
    # sig2 (the .sig of the non-local var) must NOT appear in the use table
    assert stm not in table.get_use_stms(sig2)
    # sig1 must not appear either
    assert stm not in table.get_use_stms(sig1)


# ============================================================
# AHDLUseDefDetector — enable_def / enable_use flags
# ============================================================

def test_detector_enable_def_false_suppresses_def():
    """Setting enable_def=False before visiting prevents def registration."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_dst = make_signal(hdl, 'no_def', tags={'reg'})
    stm = AHDL_NOP('placeholder')
    table = UseDefTable()
    detector = AHDLUseDefDetector()
    detector.table = table
    detector.enable_def = False
    detector.current_stm = stm
    var = AHDL_VAR(sig_dst, Ctx.STORE)
    detector.visit_AHDL_VAR(var)
    assert stm not in table.get_def_stms(sig_dst)


def test_detector_enable_use_false_suppresses_use():
    """Setting enable_use=False before visiting prevents use registration."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_src = make_signal(hdl, 'no_use', tags={'reg'})
    stm = AHDL_NOP('placeholder')
    table = UseDefTable()
    detector = AHDLUseDefDetector()
    detector.table = table
    detector.enable_use = False
    detector.current_stm = stm
    var = AHDL_VAR(sig_src, Ctx.LOAD)
    detector.visit_AHDL_VAR(var)
    assert stm not in table.get_use_stms(sig_src)


# ============================================================
# AHDLUseDefDetector — visit_AHDL_SEQ
# ============================================================

def test_detector_visit_ahdl_seq_resets_flags():
    """visit_AHDL_SEQ calls the factor's visitor and resets enable_use/enable_def."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_dst = make_signal(hdl, 'seq_dst', tags={'reg'})
    inner_stm = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_CONST(1))
    seq = AHDL_SEQ(inner_stm, 0, 1)
    block = AHDL_BLOCK('blk', (seq,))
    stg, _ = make_stg_with_state(hdl, block)
    hdl.add_fsm('seq_fsm', scope)
    hdl.add_fsm_stg('seq_fsm', [stg])

    detector = AHDLUseDefDetector()
    # Manually disable flags before processing to confirm they are reset to True
    detector.enable_use = False
    detector.enable_def = False
    detector.process(hdl)
    # After process completes, flags must have been reset to True by visit_AHDL_SEQ
    assert detector.enable_use is True
    assert detector.enable_def is True


def test_detector_visit_ahdl_seq_records_inner_stm_def():
    """visit_AHDL_SEQ dispatches to the inner factor and records its def."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_dst = make_signal(hdl, 'seq_inner_dst', tags={'reg'})
    inner_stm = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_CONST(42))
    seq = AHDL_SEQ(inner_stm, 0, 1)
    block = AHDL_BLOCK('blk', (seq,))
    stg, _ = make_stg_with_state(hdl, block)
    hdl.add_fsm('seq2_fsm', scope)
    hdl.add_fsm_stg('seq2_fsm', [stg])

    detector = AHDLUseDefDetector()
    table = detector.process(hdl)
    # The SEQ wraps an AHDL_MOVE; AHDLVisitor sets current_stm to the SEQ itself,
    # but visit_AHDL_SEQ directly calls visit_AHDL_MOVE on the factor so the
    # current_stm at the time of the VAR visit is the SEQ node.
    def_stms = table.get_def_stms(sig_dst)
    assert len(def_stms) > 0


# ============================================================
# AHDLUseDefDetector — both def and use in the same AHDL_MOVE
# ============================================================

def test_detector_move_records_both_def_and_use():
    """An AHDL_MOVE's dst is a def and src is a use."""
    scope = build_scope()
    hdl = make_hdlmodule(scope)
    sig_dst = make_signal(hdl, 'mv_dst', tags={'reg'})
    sig_src = make_signal(hdl, 'mv_src', tags={'reg'})
    stm = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_VAR(sig_src, Ctx.LOAD))
    hdl_m, stg, state = make_hdlmodule_with_fsm(stm)
    detector = AHDLUseDefDetector()
    table = detector.process(hdl_m)
    assert stm in table.get_def_stms(sig_dst)
    assert stm in table.get_use_stms(sig_src)
    assert sig_dst in table.get_sigs_defined_at(stm)
    assert sig_src in table.get_sigs_used_at(stm)
