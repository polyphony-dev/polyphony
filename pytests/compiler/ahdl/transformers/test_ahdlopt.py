"""Tests for AHDLCopyOpt and AHDLVarReducer in ahdl/transformers/ahdlopt.py.

Covers uncovered lines: 11-17, 20-26, 31-39, 42-58, 63-64, 67-82, 85-88, 91-94, 97-100.
"""
import pytest

from polyphony.compiler.ahdl.transformers.ahdlopt import AHDLCopyOpt, AHDLVarReducer
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_MOVE, AHDL_ASSIGN, AHDL_VAR, AHDL_CONST,
    AHDL_IO_READ, AHDL_TRANSITION, State,
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

_SCOPE_SRC = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
'''


def build_scope():
    setup_test()
    parser = IrReader(_SCOPE_SRC)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def make_module_with_states(hdl, states_codes):
    """Build an FSM with multiple states.

    states_codes: list of (state_name, codes_tuple) pairs.
    Returns (hdl, fsm, stg).
    """
    state_sig = hdl.gen_sig('state_v', 4, {'reg'})
    scope = hdl.scope
    fsm = FSM('main_fsm', scope, state_sig)
    stg = STG('main', None, hdl)
    states = []
    for i, (name, codes) in enumerate(states_codes):
        block = AHDL_BLOCK(name, codes)
        state = stg.new_state(name, block, i)
        states.append(state)
    stg.add_states(states)
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm
    return hdl, fsm, stg


def _get_state_codes(stg, state_name):
    return stg.get_state(state_name).block.codes


# ============================================================
# AHDLCopyOpt — _get_new_src
# ============================================================

def test_get_new_src_move():
    """_get_new_src returns AHDL_MOVE.src for AHDL_MOVE input."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('gnm_a', 32, {'reg'})
    sig_b = hdl.gen_sig('gnm_b', 32, {'reg'})

    move = AHDL_MOVE(
        AHDL_VAR(sig_b, Ctx.STORE),
        AHDL_CONST(7),
    )
    opt = AHDLCopyOpt()
    result = opt._get_new_src(move)
    assert result == AHDL_CONST(7)


def test_get_new_src_assign():
    """_get_new_src returns AHDL_ASSIGN.src for AHDL_ASSIGN input."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('gna_a', 32, {'net'})

    assign = AHDL_ASSIGN(
        AHDL_VAR(sig_a, Ctx.STORE),
        AHDL_CONST(3),
    )
    opt = AHDLCopyOpt()
    result = opt._get_new_src(assign)
    assert result == AHDL_CONST(3)


def test_get_new_src_io_read():
    """_get_new_src returns AHDL_IO_READ.io for AHDL_IO_READ input."""
    hdl = make_hdlmodule()
    sig_io = hdl.gen_sig('gnr_io', 32, {'reg'})
    sig_dst = hdl.gen_sig('gnr_dst', 32, {'reg'})

    io_var = AHDL_VAR(sig_io, Ctx.LOAD)
    dst_var = AHDL_VAR(sig_dst, Ctx.STORE)
    io_read = AHDL_IO_READ(io=io_var, dst=dst_var, is_self=False)

    opt = AHDLCopyOpt()
    result = opt._get_new_src(io_read)
    assert result is io_var


# ============================================================
# AHDLCopyOpt — _is_ignore_case
# ============================================================

def test_is_ignore_case_store_ctx():
    """STORE ctx is always ignored (not propagated)."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('iic_store', 32, {'reg'})
    var = AHDL_VAR(sig, Ctx.STORE)
    opt = AHDLCopyOpt()
    assert opt._is_ignore_case(var) is True


def test_is_ignore_case_non_local_var():
    """Non-local var (tuple of signals) is ignored."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('iic_a', 32, {'reg'})
    sig_b = hdl.gen_sig('iic_b', 32, {'reg'})
    # Multi-signal tuple makes is_local_var() return False
    var = AHDL_VAR((sig_a, sig_b), Ctx.LOAD)
    opt = AHDLCopyOpt()
    assert opt._is_ignore_case(var) is True


def test_is_ignore_case_net_signal():
    """Net signal is ignored."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('iic_net', 32, {'net'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    opt = AHDLCopyOpt()
    assert opt._is_ignore_case(var) is True


def test_is_ignore_case_regular_reg_not_ignored():
    """A plain local reg signal with LOAD ctx is not ignored."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('iic_reg', 32, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    opt = AHDLCopyOpt()
    assert opt._is_ignore_case(var) is False


# ============================================================
# AHDLCopyOpt — copy propagation via process()
# ============================================================

def test_copy_opt_propagates_const():
    """AHDLCopyOpt fully propagates a chain a=5 / b=a / out=b to out=5.

    Setup:
      S0: a <= 5      (AHDL_MOVE, a defined as const 5; int reg width 33 = effective 32 bits)
          b <= a      (AHDL_MOVE, b uses a)
          out <= b    (AHDL_MOVE, out is 'output' so AHDLVarReducer keeps it)
          ->          (AHDL_TRANSITION)

    AHDLCopyOpt runs to fixpoint:
      iteration 1: a (1 def, width match 32==32) → b's src becomes AHDL_CONST(5)
                   b (1 def, width match) → out's src becomes AHDL_CONST(5)
      AHDLVarReducer removes a and b assignments (both are now unused)
      Final: out <= 5  (only the output move remains alongside the transition)
    """
    hdl = make_hdlmodule()
    # Use 33-bit int reg: effective width = width - 1 = 32, matching AHDL_CONST default
    sig_a = hdl.gen_sig('cpa_a', 33, {'reg', 'int'})
    sig_b = hdl.gen_sig('cpa_b', 33, {'reg', 'int'})
    # sig_out is an output so AHDLVarReducer will not remove the move that writes to it
    sig_out = hdl.gen_sig('cpa_out', 33, {'reg', 'int', 'output'})

    move_a = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(5))
    move_b = AHDL_MOVE(AHDL_VAR(sig_b, Ctx.STORE), AHDL_VAR(sig_a, Ctx.LOAD))
    move_out = AHDL_MOVE(AHDL_VAR(sig_out, Ctx.STORE), AHDL_VAR(sig_b, Ctx.LOAD))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (move_a, move_b, move_out, trans))])

    AHDLCopyOpt().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    # After full fixpoint propagation, only the output move should remain (plus transition).
    # a and b are both dead and removed by AHDLVarReducer.
    # The output move should have AHDL_CONST(5) as its src.
    move_out_result = None
    for code in codes:
        if isinstance(code, AHDL_MOVE):
            if isinstance(code.dst, AHDL_VAR) and code.dst.sig == sig_out:
                move_out_result = code
                break

    assert move_out_result is not None, "Move to sig_out not found in output"
    assert isinstance(move_out_result.src, AHDL_CONST), (
        f"Expected AHDL_CONST after full copy propagation, got {type(move_out_result.src)}"
    )
    assert move_out_result.src.value == 5
    # Intermediate signals a and b should be fully eliminated
    assert not any(
        isinstance(c, AHDL_MOVE) and isinstance(c.dst, AHDL_VAR)
        and c.dst.sig in (sig_a, sig_b)
        for c in codes
    )


def test_copy_opt_no_propagation_multiple_defs():
    """AHDLCopyOpt does NOT propagate sig_a when it has multiple definitions.

    Setup:
      S0: a <= 1 / a <= 2  (sig_a has 2 defs → copy opt skips it)
          b <= a            (b gets sig_a as src, but sig_a has multiple defs so b is not propagated)
          out <= b          (out uses b; b has 1 def so b is propagated into out → out <= sig_a)
          ->

    After fixpoint:
      b's assignment is dead (out now uses sig_a directly after propagation of b→sig_a).
      sig_a's assignments survive (2 defs, output uses sig_a).
      out <= sig_a (not a constant; sig_a's 2 defs prevent the chain from resolving to AHDL_CONST).
    """
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('cpmd_a', 33, {'reg', 'int'})
    sig_b = hdl.gen_sig('cpmd_b', 33, {'reg', 'int'})
    sig_out = hdl.gen_sig('cpmd_out', 33, {'reg', 'int', 'output'})

    # Two definitions of sig_a → copy opt cannot propagate sig_a to a constant
    move_a1 = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(1))
    move_a2 = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(2))
    move_b = AHDL_MOVE(AHDL_VAR(sig_b, Ctx.STORE), AHDL_VAR(sig_a, Ctx.LOAD))
    move_out = AHDL_MOVE(AHDL_VAR(sig_out, Ctx.STORE), AHDL_VAR(sig_b, Ctx.LOAD))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(
        hdl, [('S0', (move_a1, move_a2, move_b, move_out, trans))]
    )

    AHDLCopyOpt().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    # out should end up using sig_a directly (b was propagated away, sig_a is not a const)
    move_out_result = None
    for code in codes:
        if isinstance(code, AHDL_MOVE):
            if isinstance(code.dst, AHDL_VAR) and code.dst.sig == sig_out:
                move_out_result = code
                break

    assert move_out_result is not None, "Move to sig_out not found"
    # The output should NOT be a constant (sig_a was not reducible)
    assert not isinstance(move_out_result.src, AHDL_CONST), (
        "Expected sig_a (not a constant) after failed propagation with 2 defs"
    )


def test_copy_opt_no_propagation_width_mismatch():
    """AHDLCopyOpt does NOT propagate when source and target widths differ.

    sig_a is an 'int' reg of width 17 (effective 16 bits).
    AHDL_CONST always reports env.config.default_int_width (32) bits.
    16 != 32, so copy propagation from const into sig_a is skipped.

    Similarly, propagation of sig_a (16-bit) into sig_b (also 16-bit) works
    because widths match, so sig_b is eliminated and out uses sig_a directly.
    sig_a's assignment (a <= CONST(5)) survives because propagating CONST(5) into
    sig_a's use would require matching widths (32 vs 16) which fails.

    Final state after fixpoint: a <= 5 / out <= a (sig_b eliminated, no const in out)
    """
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('cpwm_a', 17, {'reg', 'int'})   # effective width 16
    sig_b = hdl.gen_sig('cpwm_b', 17, {'reg', 'int'})
    sig_out = hdl.gen_sig('cpwm_out', 17, {'reg', 'int', 'output'})

    # sig_a <= CONST(5): const width=32, sig_a effective=16 → width mismatch, no propagation
    move_a = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(5))
    move_b = AHDL_MOVE(AHDL_VAR(sig_b, Ctx.STORE), AHDL_VAR(sig_a, Ctx.LOAD))
    move_out = AHDL_MOVE(AHDL_VAR(sig_out, Ctx.STORE), AHDL_VAR(sig_b, Ctx.LOAD))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (move_a, move_b, move_out, trans))])

    AHDLCopyOpt().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    # Width mismatch prevents constant from being propagated all the way to out.
    # sig_a's assignment survives; out ends up using sig_a (not a constant).
    move_out_result = None
    for code in codes:
        if isinstance(code, AHDL_MOVE):
            if isinstance(code.dst, AHDL_VAR) and code.dst.sig == sig_out:
                move_out_result = code
                break

    assert move_out_result is not None, "Move to sig_out not found"
    # The output src must not be a constant (width mismatch prevented propagation)
    assert not isinstance(move_out_result.src, AHDL_CONST), (
        "Width mismatch should prevent AHDL_CONST from reaching sig_out"
    )
    # sig_a's assignment (a <= 5) must still be present since it was not propagated away
    assert any(
        isinstance(c, AHDL_MOVE) and isinstance(c.dst, AHDL_VAR) and c.dst.sig == sig_a
        for c in codes
    ), "sig_a assignment should survive when width mismatch prevents propagation"


# ============================================================
# AHDLVarReducer — _can_reduce
# ============================================================

def test_var_reducer_removes_unused_move():
    """AHDLVarReducer removes AHDL_MOVE whose dst is unused."""
    hdl = make_hdlmodule()
    sig_unused = hdl.gen_sig('vru_unused', 32, {'reg'})

    move = AHDL_MOVE(AHDL_VAR(sig_unused, Ctx.STORE), AHDL_CONST(0))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (move, trans))])

    AHDLVarReducer().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    # The AHDL_MOVE should be eliminated; only AHDL_TRANSITION should remain
    assert not any(isinstance(c, AHDL_MOVE) for c in codes)


def test_var_reducer_keeps_move_with_used_dst():
    """AHDLVarReducer keeps AHDL_MOVE whose dst is subsequently used."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('vru_a', 32, {'reg'})
    sig_b = hdl.gen_sig('vru_b', 32, {'reg'})

    move_a = AHDL_MOVE(AHDL_VAR(sig_a, Ctx.STORE), AHDL_CONST(1))
    move_b = AHDL_MOVE(AHDL_VAR(sig_b, Ctx.STORE), AHDL_VAR(sig_a, Ctx.LOAD))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (move_a, move_b, trans))])

    AHDLVarReducer().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    # move_a dst (sig_a) is used by move_b → must be kept
    dsts = [c.dst.sig for c in codes if isinstance(c, AHDL_MOVE)]
    assert sig_a in dsts


def test_var_reducer_keeps_move_with_output_dst():
    """AHDLVarReducer keeps AHDL_MOVE whose dst is an output signal."""
    hdl = make_hdlmodule()
    sig_out = hdl.gen_sig('vru_out', 32, {'reg', 'output'})

    move = AHDL_MOVE(AHDL_VAR(sig_out, Ctx.STORE), AHDL_CONST(42))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (move, trans))])

    AHDLVarReducer().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    assert any(isinstance(c, AHDL_MOVE) for c in codes)


def test_var_reducer_keeps_move_with_connector_dst():
    """AHDLVarReducer keeps AHDL_MOVE whose dst is a connector signal."""
    hdl = make_hdlmodule()
    sig_conn = hdl.gen_sig('vru_conn', 32, {'reg', 'connector'})

    move = AHDL_MOVE(AHDL_VAR(sig_conn, Ctx.STORE), AHDL_CONST(0))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (move, trans))])

    AHDLVarReducer().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    assert any(isinstance(c, AHDL_MOVE) for c in codes)


def test_var_reducer_keeps_move_with_field_dst():
    """AHDLVarReducer keeps AHDL_MOVE whose dst is a field signal."""
    hdl = make_hdlmodule()
    sig_field = hdl.gen_sig('vru_field', 32, {'reg', 'field'})

    move = AHDL_MOVE(AHDL_VAR(sig_field, Ctx.STORE), AHDL_CONST(0))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (move, trans))])

    AHDLVarReducer().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    assert any(isinstance(c, AHDL_MOVE) for c in codes)


# ============================================================
# AHDLVarReducer — visit_AHDL_ASSIGN
# ============================================================

def test_var_reducer_removes_unused_assign():
    """AHDLVarReducer removes AHDL_ASSIGN (a decl-level statement) when dst is unused."""
    hdl = make_hdlmodule()
    sig_net = hdl.gen_sig('vra_net', 32, {'net'})

    # AHDL_ASSIGN is processed from hdlmodule.decls, not from FSM states.
    assign = AHDL_ASSIGN(AHDL_VAR(sig_net, Ctx.STORE), AHDL_CONST(0))
    hdl.decls.append(assign)

    # Still need an FSM (even if trivial) so process() does not error
    state_sig = hdl.gen_sig('vra_state', 4, {'reg'})
    fsm = FSM('main_fsm2', hdl.scope, state_sig)
    stg = STG('main2', None, hdl)
    trans = AHDL_TRANSITION('')
    block = AHDL_BLOCK('S0', (trans,))
    state = stg.new_state('S0', block, 0)
    stg.add_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm2'] = fsm

    AHDLVarReducer().process(hdl)

    # Unused net assignment should be removed from decls
    assert not any(isinstance(d, AHDL_ASSIGN) and d.dst.sig == sig_net for d in hdl.decls)


def test_var_reducer_removes_unused_io_read():
    """AHDLVarReducer removes AHDL_IO_READ when dst is unused."""
    hdl = make_hdlmodule()
    sig_io = hdl.gen_sig('vrir_io', 32, {'reg'})
    sig_dst = hdl.gen_sig('vrir_dst', 32, {'reg'})

    io_var = AHDL_VAR(sig_io, Ctx.LOAD)
    dst_var = AHDL_VAR(sig_dst, Ctx.STORE)
    io_read = AHDL_IO_READ(io=io_var, dst=dst_var, is_self=False)
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (io_read, trans))])

    AHDLVarReducer().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    # AHDL_IO_READ with unused dst should be eliminated
    assert not any(isinstance(c, AHDL_IO_READ) for c in codes)


def test_var_reducer_keeps_io_read_when_dst_used():
    """AHDLVarReducer keeps AHDL_IO_READ when its dst is subsequently used."""
    hdl = make_hdlmodule()
    sig_io = hdl.gen_sig('vrkir_io', 32, {'reg'})
    sig_dst = hdl.gen_sig('vrkir_dst', 32, {'reg'})
    sig_out = hdl.gen_sig('vrkir_out', 32, {'reg', 'output'})

    io_var = AHDL_VAR(sig_io, Ctx.LOAD)
    dst_var = AHDL_VAR(sig_dst, Ctx.STORE)
    io_read = AHDL_IO_READ(io=io_var, dst=dst_var, is_self=False)
    # Use sig_dst in a move so it has a use
    move_out = AHDL_MOVE(AHDL_VAR(sig_out, Ctx.STORE), AHDL_VAR(sig_dst, Ctx.LOAD))
    trans = AHDL_TRANSITION('')

    hdl, fsm, stg = make_module_with_states(hdl, [('S0', (io_read, move_out, trans))])

    AHDLVarReducer().process(hdl)

    codes = _get_state_codes(stg, 'S0')
    # sig_dst is used → AHDL_IO_READ must be retained
    assert any(isinstance(c, AHDL_IO_READ) for c in codes)


# ============================================================
# AHDLVarReducer — _can_reduce: non-AHDL_VAR dst returns False
# ============================================================

def test_can_reduce_returns_false_for_subscript_dst():
    """_can_reduce returns False when dst is not AHDL_VAR (e.g. AHDL_SUBSCRIPT)."""
    from polyphony.compiler.ahdl.ahdl import AHDL_SUBSCRIPT, AHDL_MEMVAR
    hdl = make_hdlmodule()
    sig_arr = hdl.gen_sig('crsub_arr', (32, 4), {'regarray'})

    memvar = AHDL_MEMVAR(sig_arr, Ctx.STORE)
    subscript = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))

    reducer = AHDLVarReducer()
    # Inject a dummy usedef table so _can_reduce doesn't fail
    from polyphony.compiler.ahdl.analysis.ahdlusedef import UseDefTable
    reducer.usedef = UseDefTable()

    # AHDL_SUBSCRIPT is not AHDL_VAR → _can_reduce must return False
    assert reducer._can_reduce(subscript) is False
