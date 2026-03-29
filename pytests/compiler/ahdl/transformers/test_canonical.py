"""Tests covering uncovered lines in polyphony/compiler/ahdl/transformers/canonical.py."""
import pytest

from polyphony.compiler.ahdl.transformers.canonical import Canonicalizer, FlattenStaticFieldSignals
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_MOVE, AHDL_NOP, AHDL_VAR, AHDL_MEMVAR,
    AHDL_ASSIGN, AHDL_TRANSITION, AHDL_IF, AHDL_SUBSCRIPT, AHDL_EVENT_TASK,
    AHDL_CASE, AHDL_CASE_ITEM, AHDL_META_OP, AHDL_OP, State,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule, FSM
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


_SRC = '''
scope test
tags function returnable
'''

_TB_SRC = '''
scope tb_test
tags testbench returnable
'''


def build_scope(src=_SRC):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule(src=_SRC):
    scope = build_scope(src)
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def _build_minimal_fsm(hdl, state_codes=None):
    """Create one FSM with one STG and two states (INIT, S1).

    state_codes: tuple of AHDL_STM for INIT block. Default: (AHDL_TRANSITION('S1'),).
    Returns (fsm, stg, state_init, state_s1).
    """
    state_sig = hdl.gen_sig('fsm_state', 4, {'reg'})
    scope = hdl.scope
    fsm = FSM('main_fsm', scope, state_sig)
    stg = STG('main', None, hdl)

    block_s1 = AHDL_BLOCK('S1', ())
    state_s1 = stg.new_state('S1', block_s1, 1)

    if state_codes is None:
        trans = AHDL_TRANSITION('S1')
        block_init = AHDL_BLOCK('INIT', (trans,))
    else:
        block_init = AHDL_BLOCK('INIT', state_codes)
    state_init = stg.new_state('INIT', block_init, 0)

    stg.set_states([state_init, state_s1])
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm
    return fsm, stg, state_init, state_s1


# ============================================================
# _add_reserved_signals — lines 16-22
# ============================================================

def test_add_reserved_signals_function_scope_gets_net_input():
    """Non-testbench scope: clk and rst get 'net' and 'input' tags."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()
    clk = hdl.signal('clk')
    rst = hdl.signal('rst')
    assert clk is not None
    assert rst is not None
    assert 'net' in clk.tags
    assert 'input' in clk.tags
    assert 'net' in rst.tags
    assert 'input' in rst.tags


def test_add_reserved_signals_testbench_scope_gets_reg():
    """Testbench scope: clk and rst get 'reg' tag only."""
    hdl = make_hdlmodule(_TB_SRC)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()
    clk = hdl.signal('clk')
    rst = hdl.signal('rst')
    assert clk is not None
    assert 'reg' in clk.tags
    assert 'input' not in clk.tags
    assert 'reg' in rst.tags


# ============================================================
# _add_state_constants — lines 37-43
# ============================================================

def test_add_state_constants_creates_constants():
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    # Constants for INIT (0) and S1 (1) must exist
    const_vals = {sig.name: val for sig, val in hdl.constants.items()}
    assert 'INIT' in const_vals
    assert const_vals['INIT'] == 0
    assert 'S1' in const_vals
    assert const_vals['S1'] == 1


def test_add_state_constants_updates_state_var_width():
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    # 2 states -> i=2 -> bit_length() == 2
    assert fsm.state_var.width == (2).bit_length()


# ============================================================
# _build_reset_block — lines 45-60
# ============================================================

def test_build_reset_block_empty_reset_stms():
    """With no reset_stms the block has only the AHDL_MOVE to INIT."""
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    block = c._build_reset_block(fsm)
    assert isinstance(block, AHDL_BLOCK)
    assert len(block.codes) == 1  # only the state-variable reset MOVE
    mv = block.codes[0]
    assert isinstance(mv, AHDL_MOVE)


def test_build_reset_block_reg_dst_reset_stm_kept():
    """reset_stm with reg dst is kept in the reset block."""
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    reg_sig = hdl.gen_sig('outreg', 8, {'reg'})
    reset_mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(0))
    fsm.reset_stms.append(reset_mv)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    block = c._build_reset_block(fsm)
    # The reg reset MOVE + the state-variable reset MOVE
    assert len(block.codes) == 2


def test_build_reset_block_net_dst_reset_stm_skipped():
    """reset_stm with net dst is filtered out of the reset block."""
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    net_sig = hdl.gen_sig('outnet', 8, {'net'})
    reset_mv = AHDL_MOVE(AHDL_VAR(net_sig, Ctx.STORE), AHDL_CONST(0))
    fsm.reset_stms.append(reset_mv)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    block = c._build_reset_block(fsm)
    # Only the state-variable reset MOVE; net one is skipped
    assert len(block.codes) == 1


# ============================================================
# _build_case_block and _build_case_items — lines 62-80
# ============================================================

def test_build_case_block_returns_ahdl_block_with_case():
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    block = c._build_case_block(fsm)
    assert isinstance(block, AHDL_BLOCK)
    assert len(block.codes) == 1
    assert isinstance(block.codes[0], AHDL_CASE)


def test_build_case_items_count():
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    items = c._build_case_items(fsm)
    assert len(items) == 2  # INIT and S1


def test_build_case_items_are_case_item_instances():
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)
    items = c._build_case_items(fsm)
    for item in items:
        assert isinstance(item, AHDL_CASE_ITEM)


# ============================================================
# visit_AHDL_TRANSITION — lines 191-196
# ============================================================

def test_visit_ahdl_transition_converts_to_move():
    """visit_AHDL_TRANSITION produces an AHDL_MOVE targeting current_state_sig."""
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c.current_state_sig = fsm.state_var
    c._add_state_constants(fsm)

    trans = AHDL_TRANSITION('S1')
    result = c.visit_AHDL_TRANSITION(trans)
    assert isinstance(result, AHDL_MOVE)
    assert isinstance(result.dst, AHDL_VAR)
    assert result.dst.sig is fsm.state_var
    assert result.dst.ctx == Ctx.STORE
    assert isinstance(result.src, AHDL_VAR)
    assert result.src.ctx == Ctx.LOAD


# ============================================================
# visit_AHDL_MOVE — lines 162-171
# ============================================================

def test_visit_ahdl_move_net_dst_creates_static_assignment_and_returns_nop():
    """AHDL_MOVE with a net dst -> add_static_assignment + return AHDL_NOP."""
    hdl = make_hdlmodule()
    _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()

    net_sig = hdl.gen_sig('wire_out', 8, {'net'})
    src = AHDL_CONST(42)
    mv = AHDL_MOVE(AHDL_VAR(net_sig, Ctx.STORE), src)
    result = c.visit_AHDL_MOVE(mv)

    assert isinstance(result, AHDL_NOP)
    assigns = hdl.get_static_assignment()
    assert len(assigns) == 1
    assert isinstance(assigns[0], AHDL_ASSIGN)


def test_visit_ahdl_move_netarray_dst_creates_static_assignment_and_returns_nop():
    """AHDL_MOVE with AHDL_SUBSCRIPT + netarray memvar -> static assignment + NOP."""
    hdl = make_hdlmodule()
    _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()

    netarr_sig = hdl.gen_sig('net_arr', (8, 4), {'netarray'})
    memvar = AHDL_MEMVAR(netarr_sig, Ctx.STORE)
    subscript = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    src = AHDL_CONST(7)
    mv = AHDL_MOVE(subscript, src)
    result = c.visit_AHDL_MOVE(mv)

    assert isinstance(result, AHDL_NOP)
    assigns = hdl.get_static_assignment()
    assert len(assigns) == 1


def test_visit_ahdl_move_reg_dst_passthrough():
    """AHDL_MOVE with a reg dst is returned as a new AHDL_MOVE."""
    hdl = make_hdlmodule()
    _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()

    reg_sig = hdl.gen_sig('reg_out', 8, {'reg'})
    src = AHDL_CONST(5)
    mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), src)
    result = c.visit_AHDL_MOVE(mv)

    assert isinstance(result, AHDL_MOVE)
    assert result.dst.sig is reg_sig
    assert result.src == AHDL_CONST(5)


# ============================================================
# _process_fsm — lines 24-35
# ============================================================

def test_process_fsm_creates_task_and_clears_fsms():
    hdl = make_hdlmodule()
    _build_minimal_fsm(hdl)
    assert len(hdl.fsms) == 1
    c = Canonicalizer()
    c.process(hdl)
    # After process, fsms are cleared and a task is created
    assert len(hdl.fsms) == 0
    assert len(hdl.tasks) >= 1
    assert isinstance(hdl.tasks[0], AHDL_EVENT_TASK)


def test_process_adds_clk_rst_signals():
    hdl = make_hdlmodule()
    _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.process(hdl)
    assert hdl.signal('clk') is not None
    assert hdl.signal('rst') is not None


def test_process_no_fsm_no_tasks():
    """Module with no FSMs and no edge_detectors/clock_signal: process adds clk/rst only."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.process(hdl)
    assert len(hdl.fsms) == 0
    assert len(hdl.tasks) == 0
    assert hdl.signal('clk') is not None


# ============================================================
# _process_edge_detector — lines 85-113
# ============================================================

def test_process_edge_detector_no_detectors_is_noop():
    """When no edge_detectors, the method returns early without creating tasks."""
    hdl = make_hdlmodule()
    _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.process(hdl)
    # The FSM task is created but no edge-detection tasks
    # All tasks are event tasks from FSM only
    assert len(hdl.tasks) == 1


def test_process_edge_detector_creates_delayed_task():
    """With edge_detectors, a delayed signal and task are created."""
    hdl = make_hdlmodule()
    # No FSM — just directly set up edge_detector scenario
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()

    # Create the signal for the var being watched
    watched_sig = hdl.gen_sig('my_port', 1, {'reg'})
    watched_var = AHDL_VAR(watched_sig, Ctx.LOAD)
    old_val = AHDL_CONST(0)
    new_val = AHDL_CONST(1)

    # Pre-create the detect_var signal (normally done by visit_AHDL_META_OP_edge)
    detect_var_name = f'is_{watched_var.hdl_name}_change_{old_val}_to_{new_val}'
    hdl.gen_sig(detect_var_name, 1, {'net'})

    hdl.add_edge_detector(watched_var, old_val, new_val)
    c._process_edge_detector()

    # A delayed signal should have been created
    delayed_name = f'{watched_var.hdl_name}_d'
    delayed_sig = hdl.signal(delayed_name)
    assert delayed_sig is not None
    assert 'reg' in delayed_sig.tags

    # A task for the delay register should exist
    assert len(hdl.tasks) >= 1

    # A static assignment for the edge detection should have been created
    assigns = hdl.get_static_assignment()
    assert len(assigns) >= 1


# ============================================================
# _process_clock_counter — lines 115-131
# ============================================================

def test_process_clock_counter_no_clock_signal_is_noop():
    """When clock_signal is None, no extra task is created."""
    hdl = make_hdlmodule()
    _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()
    c._process_clock_counter()
    # No tasks created by clock counter
    assert len(hdl.tasks) == 0


def test_process_clock_counter_creates_task():
    """When clock_signal is set, a clock counter task is created."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()
    # Trigger clock_signal creation
    hdl.get_clock_signal()
    assert hdl.clock_signal is not None
    c._process_clock_counter()
    assert len(hdl.tasks) == 1
    assert isinstance(hdl.tasks[0], AHDL_EVENT_TASK)


# ============================================================
# Full process() integration with FSM
# ============================================================

def test_process_full_integration():
    """Full process(): FSM converted, clk/rst added, tasks created."""
    hdl = make_hdlmodule()
    fsm, stg, state_init, state_s1 = _build_minimal_fsm(hdl)
    c = Canonicalizer()
    c.process(hdl)

    # FSM cleared
    assert len(hdl.fsms) == 0

    # clk and rst present
    clk = hdl.signal('clk')
    rst = hdl.signal('rst')
    assert clk is not None
    assert rst is not None

    # Task created (the always block)
    assert len(hdl.tasks) >= 1
    task = hdl.tasks[0]
    assert isinstance(task, AHDL_EVENT_TASK)

    # The top_if inside the task is an AHDL_IF
    assert isinstance(task.stm, AHDL_IF)


# ============================================================
# FlattenStaticFieldSignals — lines 199-216
# ============================================================

def test_flatten_local_var_unchanged():
    """visit_AHDL_VAR with a local var (single sig) returns the same AHDL_VAR."""
    hdl = make_hdlmodule()
    reg_sig = hdl.gen_sig('local_r', 8, {'reg'})
    var = AHDL_VAR(reg_sig, Ctx.LOAD)
    assert var.is_local_var() is True

    f = FlattenStaticFieldSignals()
    f.hdlmodule = hdl
    result = f.visit_AHDL_VAR(var)
    assert result is var


def test_flatten_local_memvar_unchanged():
    """visit_AHDL_MEMVAR with a local var (single sig) returns the same AHDL_MEMVAR."""
    hdl = make_hdlmodule()
    arr_sig = hdl.gen_sig('local_arr', 8, {'reg'})
    mvar = AHDL_MEMVAR(arr_sig, Ctx.LOAD)
    assert mvar.is_local_var() is True

    f = FlattenStaticFieldSignals()
    f.hdlmodule = hdl
    result = f.visit_AHDL_MEMVAR(mvar)
    assert result is mvar


# ============================================================
# visit_AHDL_META_OP_edge — lines 134-149
# ============================================================

def test_visit_meta_op_edge_single_var():
    """visit_AHDL_META_OP with op='edge' and one var creates detect signal and returns var."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.hdlmodule = hdl

    sig = hdl.gen_sig('my_sig', 1, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    old = AHDL_CONST(0)
    new = AHDL_CONST(1)
    meta = AHDL_META_OP('edge', old, new, var)

    result = c.visit_AHDL_META_OP(meta)
    assert result is not None
    # A detect_var signal should have been created
    assert hdl.signal(f'is_{sig.name}_change_0_to_1') is not None


def test_visit_meta_op_edge_multiple_vars():
    """visit_AHDL_META_OP_edge with 2+ vars returns an AHDL_OP('And', ...)."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.hdlmodule = hdl

    sig1 = hdl.gen_sig('sig_a', 1, {'reg'})
    sig2 = hdl.gen_sig('sig_b', 1, {'reg'})
    var1 = AHDL_VAR(sig1, Ctx.LOAD)
    var2 = AHDL_VAR(sig2, Ctx.LOAD)
    old = AHDL_CONST(0)
    new = AHDL_CONST(1)
    meta = AHDL_META_OP('edge', old, new, var1, var2)

    result = c.visit_AHDL_META_OP(meta)
    assert result is not None
    assert isinstance(result, AHDL_OP)
    assert result.op == 'And'


# ============================================================
# visit_AHDL_META_OP_cond — lines 151-160
# ============================================================

def test_visit_meta_op_cond_single_group():
    """visit_AHDL_META_OP_cond with one group (3 args) returns an AHDL_OP."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.hdlmodule = hdl

    port_sig = hdl.gen_sig('port_x', 8, {'reg'})
    port_var = AHDL_VAR(port_sig, Ctx.LOAD)
    meta = AHDL_META_OP('cond', 'Eq', AHDL_CONST(1), port_var)

    result = c.visit_AHDL_META_OP(meta)
    assert isinstance(result, AHDL_OP)
    assert result.op == 'Eq'


def test_visit_meta_op_cond_multiple_groups():
    """visit_AHDL_META_OP_cond with two groups combines them with And."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.hdlmodule = hdl

    sig1 = hdl.gen_sig('p1', 8, {'reg'})
    sig2 = hdl.gen_sig('p2', 8, {'reg'})
    v1 = AHDL_VAR(sig1, Ctx.LOAD)
    v2 = AHDL_VAR(sig2, Ctx.LOAD)
    meta = AHDL_META_OP('cond', 'Eq', AHDL_CONST(1), v1, 'Eq', AHDL_CONST(2), v2)

    result = c.visit_AHDL_META_OP(meta)
    assert isinstance(result, AHDL_OP)
    assert result.op == 'And'


# ============================================================
# duplicate edge detector — line 104
# ============================================================

def test_process_edge_detector_duplicate_skipped():
    """Adding the same edge (same detect_var_name) twice only creates one static assignment."""
    hdl = make_hdlmodule()
    c = Canonicalizer()
    c.hdlmodule = hdl
    c._add_reserved_signals()

    watched_sig = hdl.gen_sig('dup_port', 1, {'reg'})
    watched_var = AHDL_VAR(watched_sig, Ctx.LOAD)
    old_val = AHDL_CONST(0)
    new_val = AHDL_CONST(1)

    detect_var_name = f'is_{watched_var.hdl_name}_change_{old_val}_to_{new_val}'
    hdl.gen_sig(detect_var_name, 1, {'net'})

    # Add the same edge detector twice
    hdl.add_edge_detector(watched_var, old_val, new_val)
    hdl.add_edge_detector(watched_var, old_val, new_val)

    c._process_edge_detector()

    # Only one static assignment despite two edge_detectors with same name
    assigns = hdl.get_static_assignment()
    assert len(assigns) == 1
