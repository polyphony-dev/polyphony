"""Tests for PipelineStateHelper, PipelineBuilder, and AHDLRegisterSliceTransformer."""
import dataclasses
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_IF, AHDL_MOVE, AHDL_META_WAIT,
    AHDL_NOP, AHDL_OP, AHDL_PIPELINE_GUARD, AHDL_PROCCALL,
    AHDL_SEQ, AHDL_SUBSCRIPT, AHDL_TRANSITION, AHDL_VAR,
    AHDL_MEMVAR, AHDL_IF_EXP, State,
)
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ahdl.stgbuilder import ScheduledItemQueue
from polyphony.compiler.ahdl.stg_pipeline import (
    PipelineState, PipelineStage, PipelineStateHelper,
    PipelineBuilder, WorkerPipelineBuilder, LoopPipelineBuilder,
    AHDLRegisterSliceTransformer,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

def build_scope(src):
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


def make_test_env():
    """Create a scope + HDLModule + STG for pipeline tests."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)
    stg = STG('test_stg', None, hdl)
    return scope, hdl, stg


# ============================================================
# PipelineState / PipelineStage dataclasses
# ============================================================

def test_pipeline_state_is_frozen():
    """PipelineState is a frozen dataclass extending State."""
    _, hdl, stg = make_test_env()
    blk = AHDL_BLOCK('PS', (AHDL_TRANSITION(''),))
    ps = PipelineState('PS', blk, 0, stg)
    assert isinstance(ps, State)
    assert ps.name == 'PS'


def test_pipeline_stage_has_enable_hold():
    """PipelineStage has has_enable and has_hold fields."""
    _, hdl, stg = make_test_env()
    blk = AHDL_BLOCK('stage', (AHDL_NOP('test'),))
    stage = PipelineStage('stage', blk, 0, stg, has_enable=True, has_hold=False)
    assert stage.has_enable is True
    assert stage.has_hold is False


def test_pipeline_stage_defaults():
    """PipelineStage defaults has_enable=False, has_hold=False."""
    _, hdl, stg = make_test_env()
    blk = AHDL_BLOCK('stage', (AHDL_NOP('test'),))
    stage = PipelineStage('stage', blk, 0, stg)
    assert stage.has_enable is False
    assert stage.has_hold is False


# ============================================================
# PipelineStateHelper
# ============================================================

def test_pipeline_state_helper_creates_substate_var():
    """PipelineStateHelper creates a substate variable with correct width."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 4, None, stg)
    assert helper.substate_var is not None
    assert helper.substate_var.name == 'pipe_state'
    assert 'reg' in helper.substate_var.tags
    assert 'pipeline_ctrl' in helper.substate_var.tags


def test_pipeline_state_helper_valid_signal():
    """valid_signal creates a reg signal with pipeline_ctrl tag."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = helper.valid_signal(0)
    assert sig.name == 'pipe_0_valid'
    assert 'reg' in sig.tags
    assert 'pipeline_ctrl' in sig.tags


def test_pipeline_state_helper_ready_signal():
    """ready_signal creates a net signal with pipeline_ctrl tag."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = helper.ready_signal(1)
    assert sig.name == 'pipe_1_ready'
    assert 'net' in sig.tags
    assert 'pipeline_ctrl' in sig.tags


def test_pipeline_state_helper_enable_signal():
    """enable_signal creates a net signal."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = helper.enable_signal(0)
    assert sig.name == 'pipe_0_enable'
    assert 'net' in sig.tags


def test_pipeline_state_helper_hold_signal():
    """hold_signal creates a reg signal."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = helper.hold_signal(1)
    assert sig.name == 'pipe_1_hold'
    assert 'reg' in sig.tags


def test_pipeline_state_helper_last_signal():
    """last_signal creates a reg signal."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = helper.last_signal(0)
    assert sig.name == 'pipe_0_last'
    assert 'reg' in sig.tags


def test_pipeline_state_helper_exit_signal():
    """exit_signal creates a reg signal."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = helper.exit_signal(0)
    assert sig.name == 'pipe_0_exit'
    assert 'reg' in sig.tags


def test_pipeline_state_helper_signal_caching():
    """Calling the same signal method twice returns the same Signal."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig1 = helper.valid_signal(0)
    sig2 = helper.valid_signal(0)
    assert sig1 is sig2


def test_pipeline_state_helper_new_stage():
    """new_stage creates a PipelineStage with correct attributes."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    codes = [AHDL_NOP('test')]
    stage = helper.new_stage(3, codes, has_enable=True, has_hold=False)
    assert isinstance(stage, PipelineStage)
    assert stage.name == 'pipe_3'
    assert stage.step == 3
    assert stage.has_enable is True
    assert stage.has_hold is False
    assert stage.stg is stg


def test_pipeline_state_helper_first_valid_signal():
    """first_valid_signal is stored at index 0 in valid_signals."""
    _, hdl, stg = make_test_env()
    first_valid = hdl.gen_sig('ext_valid', 1, {'reg'})
    helper = PipelineStateHelper('pipe', 2, first_valid, stg)
    assert helper.valid_signals[0] is first_valid
    # Subsequent calls should return the stored signal
    assert helper.valid_signal(0) is first_valid


def test_pipeline_state_helper_add_global_move():
    """add_global_move adds a move to whole_moves."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = hdl.gen_sig('x', 32, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(1))
    helper.add_global_move('x', mv)
    assert len(helper.whole_moves) == 1
    assert helper.whole_moves[0] is mv


def test_pipeline_state_helper_add_global_move_merge():
    """Adding global move for same symbol tries to merge with BitOr.

    NOTE: AHDL_MOVE is a frozen dataclass, so the merge path
    (mv_.src = ...) raises FrozenInstanceError. This is a known
    issue in the production code — the merge path is currently
    unreachable because _transform_wait_function filters duplicates
    before they reach add_global_move.
    """
    import dataclasses
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    sig = hdl.gen_sig('x', 32, {'reg'})
    mv1 = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(1))
    mv2 = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(2))
    helper.add_global_move('x', mv1)
    with __import__('pytest').raises(dataclasses.FrozenInstanceError):
        helper.add_global_move('x', mv2)


def test_pipeline_state_helper_valid_exp_stage0():
    """valid_exp for stage 0 returns ready signal."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    exp = helper.valid_exp(0)
    # At stage 0: valid_exp = ready(0)
    assert isinstance(exp, AHDL_VAR)
    assert exp.sig.name == 'pipe_0_ready'


def test_pipeline_state_helper_valid_exp_later_stage():
    """valid_exp for stage > 0 returns IF_EXP with hold check."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 3, None, stg)
    exp = helper.valid_exp(1)
    # At stage > 0: hold ? ready : ready & prev_valid
    assert isinstance(exp, AHDL_IF_EXP)
    # cond is the hold signal
    assert isinstance(exp.cond, AHDL_VAR)
    assert exp.cond.sig.name == 'pipe_1_hold'


# ============================================================
# PipelineBuilder._check_guard_need
# ============================================================

def test_check_guard_need_proccall():
    """AHDL_PROCCALL needs a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    ahdl = AHDL_PROCCALL('test', ())
    assert builder._check_guard_need(ahdl) is True


def test_check_guard_need_if():
    """AHDL_IF needs a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    cond = AHDL_CONST(1)
    blk = AHDL_BLOCK('', (AHDL_NOP(''),))
    ahdl = AHDL_IF((cond,), (blk,))
    assert builder._check_guard_need(ahdl) is True


def test_check_guard_need_move_reg():
    """AHDL_MOVE to a reg signal needs a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    sig = hdl.gen_sig('r', 32, {'reg'})
    ahdl = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(0))
    assert builder._check_guard_need(ahdl) is True


def test_check_guard_need_move_net():
    """AHDL_MOVE to a net signal does NOT need a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    sig = hdl.gen_sig('w', 32, {'net'})
    ahdl = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(0))
    assert builder._check_guard_need(ahdl) is False


def test_check_guard_need_move_subscript():
    """AHDL_MOVE to AHDL_SUBSCRIPT needs a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    sig = hdl.gen_sig('mem', (8, 16), {'regarray'})
    memvar = AHDL_MEMVAR(sig, Ctx.STORE)
    dst = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    ahdl = AHDL_MOVE(dst, AHDL_CONST(0))
    assert builder._check_guard_need(ahdl) is True


def test_check_guard_need_seq():
    """AHDL_SEQ needs a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    ahdl = AHDL_SEQ(AHDL_NOP(''), 0, 1)
    assert builder._check_guard_need(ahdl) is True


def test_check_guard_need_nop():
    """AHDL_NOP does NOT need a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    ahdl = AHDL_NOP('nop')
    assert builder._check_guard_need(ahdl) is False


def test_check_guard_need_transition():
    """AHDL_TRANSITION does NOT need a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    ahdl = AHDL_TRANSITION('S0')
    assert builder._check_guard_need(ahdl) is False


def test_check_guard_need_const():
    """AHDL_CONST does NOT need a guard."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    ahdl = AHDL_CONST(42)
    assert builder._check_guard_need(ahdl) is False


# ============================================================
# PipelineBuilder._is_stall_free
# ============================================================

def test_is_stall_free_no_wait():
    """Pipeline without META_WAIT is stall-free."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.scheduled_items = ScheduledItemQueue()
    sig = hdl.gen_sig('r', 32, {'reg'})
    builder.scheduled_items.push(0, AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(1)), '')
    builder.scheduled_items.push(1, AHDL_NOP('nop'), '')
    assert builder._is_stall_free() is True


def test_is_stall_free_with_wait():
    """Pipeline with META_WAIT is NOT stall-free."""
    _, hdl, stg = make_test_env()
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.scheduled_items = ScheduledItemQueue()
    builder.scheduled_items.push(0, AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(0), AHDL_CONST(1)), '')
    assert builder._is_stall_free() is False


# ============================================================
# PipelineBuilder._make_stage
# ============================================================

def test_make_stage_first_finite_loop():
    """First stage of finite loop gets has_enable=True."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = True
    builder.stages = []
    codes = [AHDL_NOP('test')]
    stage = builder._make_stage(helper, 0, codes, is_stall_free=True)
    assert stage.has_enable is True
    assert stage.has_hold is False


def test_make_stage_later_with_stall():
    """Later stages with stalls get has_hold=True."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = True
    builder.stages = []
    codes = [AHDL_NOP('test')]
    stage = builder._make_stage(helper, 1, codes, is_stall_free=False)
    assert stage.has_enable is False
    assert stage.has_hold is True


def test_make_stage_later_stall_free():
    """Later stages in stall-free pipeline get has_hold=False."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = True
    builder.stages = []
    codes = [AHDL_NOP('test')]
    stage = builder._make_stage(helper, 1, codes, is_stall_free=True)
    assert stage.has_enable is False
    assert stage.has_hold is False


def test_make_stage_first_non_finite():
    """First stage of non-finite loop does NOT get has_enable."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = False
    builder.stages = []
    codes = [AHDL_NOP('test')]
    stage = builder._make_stage(helper, 0, codes, is_stall_free=True)
    assert stage.has_enable is False


def test_make_stage_with_meta_wait():
    """Stage containing META_WAIT gets has_enable=True."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = False
    builder.stages = []
    codes = [AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(0), AHDL_CONST(1))]
    stage = builder._make_stage(helper, 2, codes, is_stall_free=False)
    assert stage.has_enable is True


# ============================================================
# PipelineBuilder._add_pipeline_guard
# ============================================================

def test_add_pipeline_guard_stage0_with_enable():
    """Stage 0 with enable uses ready(0) as guard condition."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = True
    builder.stages = []
    builder.hdlmodule = hdl

    sig = hdl.gen_sig('r', 32, {'reg'})
    codes = [AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(1))]
    stage = helper.new_stage(0, codes, has_enable=True, has_hold=False)

    new_stage = builder._add_pipeline_guard(helper, stage)
    # First code should be AHDL_PIPELINE_GUARD
    guard = new_stage.block.codes[0]
    assert isinstance(guard, AHDL_PIPELINE_GUARD)
    # Guard condition should be ready(0)
    guard_cond = guard.conds[0]
    assert isinstance(guard_cond, AHDL_VAR)
    assert guard_cond.sig.name == 'pipe_0_ready'


def test_add_pipeline_guard_stage0_no_enable():
    """Stage 0 without enable uses CONST(1) as guard condition."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = False
    builder.stages = []
    builder.hdlmodule = hdl

    sig = hdl.gen_sig('r', 32, {'reg'})
    codes = [AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(1))]
    stage = helper.new_stage(0, codes, has_enable=False, has_hold=False)

    new_stage = builder._add_pipeline_guard(helper, stage)
    guard = new_stage.block.codes[0]
    assert isinstance(guard, AHDL_PIPELINE_GUARD)
    guard_cond = guard.conds[0]
    assert isinstance(guard_cond, AHDL_CONST)
    assert guard_cond.value == 1


def test_add_pipeline_guard_later_stage():
    """Later stages use valid(step-1) as guard condition."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 3, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = True
    builder.stages = []
    builder.hdlmodule = hdl

    sig = hdl.gen_sig('r', 32, {'reg'})
    codes = [AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(1))]
    stage = helper.new_stage(2, codes, has_enable=False, has_hold=False)

    new_stage = builder._add_pipeline_guard(helper, stage)
    guard = new_stage.block.codes[0]
    assert isinstance(guard, AHDL_PIPELINE_GUARD)
    guard_cond = guard.conds[0]
    assert isinstance(guard_cond, AHDL_VAR)
    assert guard_cond.sig.name == 'pipe_1_valid'


def test_add_pipeline_guard_non_guarded_stays_outside():
    """Non-guardable codes remain outside the guard block."""
    _, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    builder = PipelineBuilder.__new__(PipelineBuilder)
    builder.is_finite_loop = True
    builder.stages = []
    builder.hdlmodule = hdl

    sig = hdl.gen_sig('r', 32, {'reg'})
    nop = AHDL_NOP('no guard')
    mv = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(1))
    codes = [nop, mv]
    stage = helper.new_stage(0, codes, has_enable=True, has_hold=False)

    new_stage = builder._add_pipeline_guard(helper, stage)
    # Guard should contain only the MOVE
    guard = new_stage.block.codes[0]
    assert isinstance(guard, AHDL_PIPELINE_GUARD)
    guard_codes = guard.blocks[0].codes
    assert len(guard_codes) == 1
    assert isinstance(guard_codes[0], AHDL_MOVE)
    # NOP should be outside the guard
    assert any(isinstance(c, AHDL_NOP) for c in new_stage.block.codes)


# ============================================================
# AHDLRegisterSliceTransformer
# ============================================================

def test_register_slice_transformer_replaces_var():
    """AHDLRegisterSliceTransformer replaces matching AHDL_VAR signals."""
    _, hdl, stg = make_test_env()
    orig_sig = hdl.gen_sig('x', 32, {'reg'})
    new_sig = hdl.gen_sig('x_2', 32, {'reg'})

    src_var = AHDL_VAR(orig_sig, Ctx.LOAD)
    dst_sig = hdl.gen_sig('y', 32, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(dst_sig, Ctx.STORE), src_var)

    # Build replace table: (id(stm), sig) -> (new_sig,)
    replace_table = {(id(mv), orig_sig): (new_sig,)}
    transformer = AHDLRegisterSliceTransformer(replace_table, {}, hdl)

    # We need to set current_stm context for the transformer
    transformer.current_stm = mv
    result = transformer.visit_AHDL_VAR(src_var)
    assert isinstance(result, AHDL_VAR)
    # When key matches, the var should be replaced
    assert result.vars == (new_sig,)


def test_register_slice_transformer_no_match():
    """AHDLRegisterSliceTransformer leaves unmatched vars unchanged."""
    _, hdl, stg = make_test_env()
    orig_sig = hdl.gen_sig('x', 32, {'reg'})
    src_var = AHDL_VAR(orig_sig, Ctx.LOAD)

    dst_sig = hdl.gen_sig('y', 32, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(dst_sig, Ctx.STORE), src_var)

    # Empty replace table
    transformer = AHDLRegisterSliceTransformer({}, {}, hdl)
    transformer.current_stm = mv
    result = transformer.visit_AHDL_VAR(src_var)
    assert result is src_var  # unchanged


# ============================================================
# PipelineBuilder.__init__ (lines 108-109)
# ============================================================

def test_pipeline_builder_init():
    """PipelineBuilder.__init__ calls super and sets is_finite_loop=True."""
    scope, hdl, stg = make_test_env()
    builder = PipelineBuilder(scope, stg, {})
    assert builder.scope is scope
    assert builder.hdlmodule is hdl
    assert builder.stg is stg
    assert builder.is_finite_loop is True


# ============================================================
# WorkerPipelineBuilder.__init__ (lines 625-627)
# ============================================================

def test_worker_pipeline_builder_init():
    """WorkerPipelineBuilder sets is_finite_loop=False."""
    scope, hdl, stg = make_test_env()
    builder = WorkerPipelineBuilder(scope, stg, {})
    assert builder.is_finite_loop is False
    assert builder.scope is scope


# ============================================================
# PipelineBuilder._make_stm2stage_num (lines 369-381)
# ============================================================

def test_make_stm2stage_num_basic():
    """_make_stm2stage_num maps each code to its stage index."""
    scope, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    nop0 = AHDL_NOP('s0')
    nop1 = AHDL_NOP('s1')
    stage0 = helper.new_stage(0, [nop0], False, False)
    stage1 = helper.new_stage(1, [nop1], False, False)

    builder = PipelineBuilder(scope, stg, {})
    builder.stages = [stage0, stage1]
    result = builder._make_stm2stage_num(helper)
    assert result[nop0] == 0
    assert result[nop1] == 1


def test_make_stm2stage_num_with_if():
    """_make_stm2stage_num recurses into AHDL_IF blocks."""
    scope, hdl, stg = make_test_env()
    helper = PipelineStateHelper('pipe', 2, None, stg)
    inner_nop = AHDL_NOP('inner')
    cond = AHDL_CONST(1)
    blk = AHDL_BLOCK('', (inner_nop,))
    if_stm = AHDL_IF((cond,), (blk,))
    stage0 = helper.new_stage(0, [if_stm], False, False)

    builder = PipelineBuilder(scope, stg, {})
    builder.stages = [stage0]
    result = builder._make_stm2stage_num(helper)
    # Both the IF itself and inner_nop should be mapped to stage 0
    assert result[if_stm] == 0
    assert result[inner_nop] == 0


# ============================================================
# LoopPipelineBuilder._add_last_signal_chain (lines 573-587)
# ============================================================

def _make_loop_builder():
    """Create a LoopPipelineBuilder without calling __init__ (avoids UseDefDetector)."""
    scope, hdl, stg = make_test_env()
    builder = LoopPipelineBuilder.__new__(LoopPipelineBuilder)
    builder.is_finite_loop = True
    builder.hdlmodule = hdl
    builder.stg = stg
    builder.scope = scope
    helper = PipelineStateHelper('pipe', 3, None, stg)
    return builder, helper, hdl, stg


def test_add_last_signal_chain_step0():
    """Step 0: l_rhs = Invert(cond), stage gains last-signal move."""
    builder, helper, hdl, stg = _make_loop_builder()
    stage0 = helper.new_stage(0, [AHDL_NOP('s0')], True, False)
    stage1 = helper.new_stage(1, [AHDL_NOP('s1')], False, False)
    builder.stages = [stage0, stage1]

    cond = AHDL_CONST(1)
    result = builder._add_last_signal_chain(helper, stage0, cond)
    assert result is not None
    # Last code should be a MOVE assigning last_signal <= Invert(cond)
    last_code = result.block.codes[-1]
    assert isinstance(last_code, AHDL_MOVE)
    assert isinstance(last_code.src, AHDL_OP)
    assert last_code.src.op == 'Invert'


def test_add_last_signal_chain_middle_stage():
    """Middle stage (step > 0, not last): l_rhs = BitAnd(prev_last, ready)."""
    builder, helper, hdl, stg = _make_loop_builder()
    stage0 = helper.new_stage(0, [AHDL_NOP('s0')], True, False)
    stage1 = helper.new_stage(1, [AHDL_NOP('s1')], False, False)
    stage2 = helper.new_stage(2, [AHDL_NOP('s2')], False, False)
    builder.stages = [stage0, stage1, stage2]

    cond = AHDL_CONST(1)
    result = builder._add_last_signal_chain(helper, stage1, cond)
    assert result is not None
    last_code = result.block.codes[-1]
    assert isinstance(last_code, AHDL_MOVE)
    assert isinstance(last_code.src, AHDL_OP)
    assert last_code.src.op == 'BitAnd'


def test_add_last_signal_chain_last_stage_returns_none():
    """Last stage: returns None (no last-signal propagation)."""
    builder, helper, hdl, stg = _make_loop_builder()
    stage0 = helper.new_stage(0, [AHDL_NOP('s0')], True, False)
    stage1 = helper.new_stage(1, [AHDL_NOP('s1')], False, False)
    builder.stages = [stage0, stage1]

    cond = AHDL_CONST(1)
    result = builder._add_last_signal_chain(helper, stage1, cond)
    assert result is None


# ============================================================
# LoopPipelineBuilder._add_control_chain_no_stall (lines 589-621)
# ============================================================

def test_add_control_chain_no_stall_step0_no_enable():
    """Step 0 without enable in a single-stage pipeline: only ready_stm added, no set_valid."""
    builder, helper, hdl, stg = _make_loop_builder()
    stage0 = helper.new_stage(0, [AHDL_NOP('s0')], has_enable=False, has_hold=False)
    builder.stages = [stage0]  # single-stage pipeline: step0 is last

    result = builder._add_control_chain_no_stall(helper, stage0)
    added = result.block.codes[len(stage0.block.codes):]
    # Only ready_stm (is_last=True, no set_valid)
    assert len(added) == 1
    assert isinstance(added[0], AHDL_MOVE)


def test_add_control_chain_no_stall_step0_with_enable():
    """Step 0 with enable: ready_rhs = BitAnd(r_next, enable)."""
    builder, helper, hdl, stg = _make_loop_builder()
    stage0 = helper.new_stage(0, [AHDL_NOP('s0')], has_enable=True, has_hold=False)
    stage1 = helper.new_stage(1, [AHDL_NOP('s1')], has_enable=False, has_hold=False)
    builder.stages = [stage0, stage1]

    result = builder._add_control_chain_no_stall(helper, stage0)
    added = result.block.codes[len(stage0.block.codes):]
    ready_stm = added[0]
    assert isinstance(ready_stm, AHDL_MOVE)
    # ready_rhs should be BitAnd(r_next, enable)
    assert isinstance(ready_stm.src, AHDL_OP)
    assert ready_stm.src.op == 'BitAnd'


def test_add_control_chain_no_stall_last_stage():
    """Last stage: r_next = CONST(1), no set_valid added."""
    builder, helper, hdl, stg = _make_loop_builder()
    stage0 = helper.new_stage(0, [AHDL_NOP('s0')], has_enable=True, has_hold=False)
    stage1 = helper.new_stage(1, [AHDL_NOP('s1')], has_enable=False, has_hold=False)
    builder.stages = [stage0, stage1]

    result = builder._add_control_chain_no_stall(helper, stage1)
    added = result.block.codes[len(stage1.block.codes):]
    # Only ready_stm (no set_valid since is_last)
    assert len(added) == 1
    ready_stm = added[0]
    assert isinstance(ready_stm.src, AHDL_CONST)
    assert ready_stm.src.value == 1


def test_add_control_chain_no_stall_middle_stage():
    """Middle stage (step > 0, not last): v_prev from valid_signal(step-1)."""
    builder, helper, hdl, stg = _make_loop_builder()
    stage0 = helper.new_stage(0, [AHDL_NOP('s0')], has_enable=True, has_hold=False)
    stage1 = helper.new_stage(1, [AHDL_NOP('s1')], has_enable=False, has_hold=False)
    stage2 = helper.new_stage(2, [AHDL_NOP('s2')], has_enable=False, has_hold=False)
    builder.stages = [stage0, stage1, stage2]

    result = builder._add_control_chain_no_stall(helper, stage1)
    added = result.block.codes[len(stage1.block.codes):]
    # ready_stm + set_valid
    assert len(added) == 2


# ============================================================
# AHDLRegisterSliceTransformer.visit_AHDL_PIPELINE_GUARD
# (lines 459-464)
# ============================================================

def test_register_slice_transformer_guard_with_slice_moves():
    """visit_AHDL_PIPELINE_GUARD appends slice moves when guard id is in slice_moves."""
    _, hdl, stg = make_test_env()
    inner_nop = AHDL_NOP('inner')
    guard = AHDL_PIPELINE_GUARD(AHDL_CONST(1), (inner_nop,))

    slice_sig = hdl.gen_sig('s_sliced', 32, {'reg'})
    slice_move = AHDL_MOVE(AHDL_VAR(slice_sig, Ctx.STORE), AHDL_CONST(0))
    slice_moves = {id(guard): [slice_move]}

    transformer = AHDLRegisterSliceTransformer({}, slice_moves, hdl)
    result = transformer.visit(guard)

    assert isinstance(result, AHDL_PIPELINE_GUARD)
    assert len(result.blocks[0].codes) == 2  # inner_nop + slice_move
    assert isinstance(result.blocks[0].codes[-1], AHDL_MOVE)


def test_register_slice_transformer_guard_without_slice_moves():
    """visit_AHDL_PIPELINE_GUARD falls through to super when not in slice_moves."""
    _, hdl, stg = make_test_env()
    inner_nop = AHDL_NOP('inner')
    guard = AHDL_PIPELINE_GUARD(AHDL_CONST(1), (inner_nop,))

    transformer = AHDLRegisterSliceTransformer({}, {}, hdl)
    result = transformer.visit(guard)

    assert isinstance(result, AHDL_PIPELINE_GUARD)
    # codes unchanged
    assert len(result.blocks[0].codes) == 1
    assert isinstance(result.blocks[0].codes[0], AHDL_NOP)
