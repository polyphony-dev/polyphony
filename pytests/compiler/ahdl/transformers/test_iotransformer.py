"""Tests for IOTransformer and WaitTransformer in ahdl/transformers/iotransformer.py.

Covers uncovered lines:
  IOTransformer : 10-32, 35-45, 48-55, 58-65, 68-76, 79, 82
  WaitTransformer: 87, 90-95, 98-104, 107-126, 129-134, 137-146, 149-159, 162-183
"""
import pytest

from polyphony.compiler.ahdl.transformers.iotransformer import IOTransformer, WaitTransformer
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_IF, AHDL_MOVE, AHDL_META_WAIT, AHDL_NOP,
    AHDL_VAR, AHDL_MEMVAR, AHDL_IO_READ, AHDL_IO_WRITE, AHDL_SEQ,
    AHDL_MODULECALL, AHDL_CALLEE_PROLOG, AHDL_CALLEE_EPILOG, State,
    AHDL_TRANSITION,
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


def make_io_transformer(hdl):
    t = IOTransformer()
    t.hdlmodule = hdl
    return t


def make_wait_transformer(hdl=None):
    t = WaitTransformer()
    if hdl is not None:
        t.hdlmodule = hdl
    return t


# ============================================================
# IOTransformer — visit_AHDL_IO_READ  (line 79)
# ============================================================

def test_visit_AHDL_IO_READ():
    """visit_AHDL_IO_READ returns AHDL_MOVE(dst, io)."""
    hdl = make_hdlmodule()
    sig_io = hdl.gen_sig('ior_io', 32, {'reg'})
    sig_dst = hdl.gen_sig('ior_dst', 32, {'reg'})

    io_var = AHDL_VAR(sig_io, Ctx.LOAD)
    dst_var = AHDL_VAR(sig_dst, Ctx.STORE)
    ahdl = AHDL_IO_READ(io=io_var, dst=dst_var, is_self=False)

    t = make_io_transformer(hdl)
    result = t.visit_AHDL_IO_READ(ahdl)

    assert isinstance(result, AHDL_MOVE)
    assert result.dst is dst_var
    assert result.src is io_var


# ============================================================
# IOTransformer — visit_AHDL_IO_WRITE  (line 82)
# ============================================================

def test_visit_AHDL_IO_WRITE():
    """visit_AHDL_IO_WRITE returns AHDL_MOVE(io, src)."""
    hdl = make_hdlmodule()
    sig_io = hdl.gen_sig('iow_io', 32, {'reg'})
    sig_src = hdl.gen_sig('iow_src', 32, {'reg'})

    io_var = AHDL_VAR(sig_io, Ctx.STORE)
    src_var = AHDL_VAR(sig_src, Ctx.LOAD)
    ahdl = AHDL_IO_WRITE(io=io_var, src=src_var, is_self=False)

    t = make_io_transformer(hdl)
    result = t.visit_AHDL_IO_WRITE(ahdl)

    assert isinstance(result, AHDL_MOVE)
    assert result.dst is io_var
    assert result.src is src_var


# ============================================================
# IOTransformer — call_sequence  (lines 10-32)
# ============================================================

def _make_hdl_with_inst_signals(inst_name='inst'):
    """Build an HDLModule that already has ready/valid/accept signals for inst_name."""
    hdl = make_hdlmodule()
    hdl.gen_sig(f'{inst_name}_valid', 1, {'reg'})
    hdl.gen_sig(f'{inst_name}_ready', 1, {'reg'})
    hdl.gen_sig(f'{inst_name}_accept', 1, {'reg'})
    return hdl


def test_call_sequence_step0():
    """Step 0: emits MOVE(ready=1) followed by MOVE(acc=arg) for each arg."""
    hdl = _make_hdl_with_inst_signals('inst')
    acc_sig = hdl.gen_sig('inst_acc_in', 32, {'reg'})

    ahdl_call = AHDL_MODULECALL(None, (AHDL_CONST(42),), 'inst', '', ())
    t = make_io_transformer(hdl)

    result = t.call_sequence(0, 2, [acc_sig], [], ahdl_call)

    assert isinstance(result, tuple)
    assert len(result) == 2
    # First statement: MOVE(ready, 1)
    ready_sig = hdl.signal('inst_ready')
    move0 = result[0]
    assert isinstance(move0, AHDL_MOVE)
    assert move0.dst == AHDL_VAR(ready_sig, Ctx.STORE)
    assert move0.src == AHDL_CONST(1)
    # Second statement: MOVE(acc, arg)
    move1 = result[1]
    assert isinstance(move1, AHDL_MOVE)
    assert move1.dst == AHDL_VAR(acc_sig, Ctx.STORE)
    assert move1.src == AHDL_CONST(42)


def test_call_sequence_step1_no_returns():
    """Step 1: emits MOVE(ready=0), META_WAIT, MOVE(accept=1); no return moves if empty."""
    hdl = _make_hdl_with_inst_signals('inst')
    ahdl_call = AHDL_MODULECALL(None, (), 'inst', '', ())
    t = make_io_transformer(hdl)

    result = t.call_sequence(1, 2, [], [], ahdl_call)

    assert isinstance(result, tuple)
    assert len(result) == 3
    ready_sig = hdl.signal('inst_ready')
    accept_sig = hdl.signal('inst_accept')

    move0 = result[0]
    assert isinstance(move0, AHDL_MOVE)
    assert move0.dst == AHDL_VAR(ready_sig, Ctx.STORE)
    assert move0.src == AHDL_CONST(0)

    wait = result[1]
    assert isinstance(wait, AHDL_META_WAIT)
    assert wait.metaid == 'WAIT_COND'

    move2 = result[2]
    assert isinstance(move2, AHDL_MOVE)
    assert move2.dst == AHDL_VAR(accept_sig, Ctx.STORE)
    assert move2.src == AHDL_CONST(1)


def test_call_sequence_step1_with_returns():
    """Step 1: return signals are copied from acc to ret."""
    hdl = _make_hdl_with_inst_signals('inst')
    acc_sig = hdl.gen_sig('inst_acc_out', 32, {'reg'})
    ret_sig = hdl.gen_sig('inst_ret', 32, {'reg'})
    ret_var = AHDL_VAR(ret_sig, Ctx.STORE)

    ahdl_call = AHDL_MODULECALL(None, (), 'inst', '', (ret_var,))
    t = make_io_transformer(hdl)

    result = t.call_sequence(1, 2, [], [acc_sig], ahdl_call)

    assert isinstance(result, tuple)
    assert len(result) == 4
    # Third entry should be MOVE(ret, acc)
    move_ret = result[2]
    assert isinstance(move_ret, AHDL_MOVE)
    assert move_ret.dst is ret_var
    assert move_ret.src == AHDL_VAR(acc_sig, Ctx.LOAD)


def test_call_sequence_step2():
    """Step 2: emits MOVE(accept=0)."""
    hdl = _make_hdl_with_inst_signals('inst')
    ahdl_call = AHDL_MODULECALL(None, (), 'inst', '', ())
    t = make_io_transformer(hdl)

    result = t.call_sequence(2, 2, [], [], ahdl_call)

    assert isinstance(result, tuple)
    assert len(result) == 1
    accept_sig = hdl.signal('inst_accept')
    move0 = result[0]
    assert isinstance(move0, AHDL_MOVE)
    assert move0.dst == AHDL_VAR(accept_sig, Ctx.STORE)
    assert move0.src == AHDL_CONST(0)


# ============================================================
# IOTransformer — visit_AHDL_CALLEE_PROLOG_SEQ  (lines 48-55)
# ============================================================

def test_visit_AHDL_CALLEE_PROLOG_SEQ_step0():
    """Step 0: returns (MOVE(valid=0), META_WAIT(ready==1))."""
    hdl = make_hdlmodule()
    # hdl.name == 'test'  →  signals must be 'test_valid' and 'test_ready'
    hdl.gen_sig('test_valid', 1, {'reg'})
    hdl.gen_sig('test_ready', 1, {'reg'})

    t = make_io_transformer(hdl)
    result = t.visit_AHDL_CALLEE_PROLOG_SEQ(AHDL_CALLEE_PROLOG('test'), 0, 1)

    assert isinstance(result, tuple)
    assert len(result) == 2

    unset_valid = result[0]
    assert isinstance(unset_valid, AHDL_MOVE)
    valid_sig = hdl.signal('test_valid')
    assert unset_valid.dst == AHDL_VAR(valid_sig, Ctx.STORE)
    assert unset_valid.src == AHDL_CONST(0)

    wait_ready = result[1]
    assert isinstance(wait_ready, AHDL_META_WAIT)
    assert wait_ready.metaid == 'WAIT_COND'


def test_visit_AHDL_CALLEE_PROLOG_SEQ_step1_asserts():
    """Step != 0 triggers AssertionError."""
    hdl = make_hdlmodule()
    hdl.gen_sig('test_valid', 1, {'reg'})
    hdl.gen_sig('test_ready', 1, {'reg'})

    t = make_io_transformer(hdl)
    with pytest.raises(AssertionError):
        t.visit_AHDL_CALLEE_PROLOG_SEQ(AHDL_CALLEE_PROLOG('test'), 1, 2)


# ============================================================
# IOTransformer — visit_AHDL_CALLEE_EPILOG_SEQ  (lines 58-65)
# ============================================================

def test_visit_AHDL_CALLEE_EPILOG_SEQ_step0():
    """Step 0: returns (MOVE(valid=1), META_WAIT(accept==1))."""
    hdl = make_hdlmodule()
    hdl.gen_sig('test_valid', 1, {'reg'})
    hdl.gen_sig('test_accept', 1, {'reg'})

    t = make_io_transformer(hdl)
    result = t.visit_AHDL_CALLEE_EPILOG_SEQ(AHDL_CALLEE_EPILOG('test'), 0, 1)

    assert isinstance(result, tuple)
    assert len(result) == 2

    set_valid = result[0]
    assert isinstance(set_valid, AHDL_MOVE)
    valid_sig = hdl.signal('test_valid')
    assert set_valid.dst == AHDL_VAR(valid_sig, Ctx.STORE)
    assert set_valid.src == AHDL_CONST(1)

    wait_accept = result[1]
    assert isinstance(wait_accept, AHDL_META_WAIT)
    assert wait_accept.metaid == 'WAIT_COND'


def test_visit_AHDL_CALLEE_EPILOG_SEQ_step1_asserts():
    """Step != 0 triggers AssertionError."""
    hdl = make_hdlmodule()
    hdl.gen_sig('test_valid', 1, {'reg'})
    hdl.gen_sig('test_accept', 1, {'reg'})

    t = make_io_transformer(hdl)
    with pytest.raises(AssertionError):
        t.visit_AHDL_CALLEE_EPILOG_SEQ(AHDL_CALLEE_EPILOG('test'), 1, 2)


# ============================================================
# IOTransformer — visit_AHDL_SEQ  (lines 68-76)
# ============================================================

def test_visit_AHDL_SEQ_prolog():
    """visit_AHDL_SEQ dispatches to visit_AHDL_CALLEE_PROLOG_SEQ and returns tuple."""
    hdl = make_hdlmodule()
    hdl.gen_sig('test_valid', 1, {'reg'})
    hdl.gen_sig('test_ready', 1, {'reg'})

    t = make_io_transformer(hdl)
    ahdl_seq = AHDL_SEQ(AHDL_CALLEE_PROLOG('test'), 0, 1)
    result = t.visit_AHDL_SEQ(ahdl_seq)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], AHDL_MOVE)
    assert isinstance(result[1], AHDL_META_WAIT)


def test_visit_AHDL_SEQ_epilog():
    """visit_AHDL_SEQ dispatches to visit_AHDL_CALLEE_EPILOG_SEQ and returns tuple."""
    hdl = make_hdlmodule()
    hdl.gen_sig('test_valid', 1, {'reg'})
    hdl.gen_sig('test_accept', 1, {'reg'})

    t = make_io_transformer(hdl)
    ahdl_seq = AHDL_SEQ(AHDL_CALLEE_EPILOG('test'), 0, 1)
    result = t.visit_AHDL_SEQ(ahdl_seq)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], AHDL_MOVE)
    assert isinstance(result[1], AHDL_META_WAIT)


def test_visit_AHDL_SEQ_propagates_dfgnode():
    """visit_AHDL_SEQ propagates dfg node entries to the generated statements."""
    hdl = make_hdlmodule()
    hdl.gen_sig('test_valid', 1, {'reg'})
    hdl.gen_sig('test_ready', 1, {'reg'})

    t = make_io_transformer(hdl)
    ahdl_seq = AHDL_SEQ(AHDL_CALLEE_PROLOG('test'), 0, 1)

    # Register a fake dfg node for the SEQ itself
    fake_node = object()
    hdl.ahdl2dfgnode[id(ahdl_seq)] = (ahdl_seq, fake_node)

    result = t.visit_AHDL_SEQ(ahdl_seq)

    # Every produced statement should now have a dfg node entry
    for stm in result:
        assert id(stm) in hdl.ahdl2dfgnode
        _, node = hdl.ahdl2dfgnode[id(stm)]
        assert node is fake_node


# ============================================================
# IOTransformer — visit_AHDL_MODULECALL_SEQ  (lines 35-45)
# ============================================================

def test_visit_AHDL_MODULECALL_SEQ_step0():
    """Builds args/returns from sub_module connections and delegates to call_sequence."""
    hdl = _make_hdl_with_inst_signals('sub')

    # Build connection signals: ctrl, input, output
    ctrl_sig = hdl.gen_sig('sub_ctrl', 1, {'ctrl', 'reg'})
    in_sig = hdl.gen_sig('sub_in_port', 32, {'input', 'reg'})
    out_sig = hdl.gen_sig('sub_out_port', 32, {'output', 'reg'})
    acc_in = hdl.gen_sig('sub_acc_in', 32, {'reg'})
    acc_out = hdl.gen_sig('sub_acc_out', 32, {'reg'})

    ctrl_var = AHDL_VAR(ctrl_sig, Ctx.LOAD)
    in_var = AHDL_VAR(in_sig, Ctx.LOAD)
    out_var = AHDL_VAR(out_sig, Ctx.LOAD)
    acc_in_var = AHDL_VAR(acc_in, Ctx.LOAD)
    acc_out_var = AHDL_VAR(acc_out, Ctx.LOAD)

    # connections: list of (var, acc) pairs
    connections = [
        (ctrl_var, acc_in_var),   # ctrl → skip
        (in_var, acc_in),         # input → goes into args
        (out_var, acc_out),       # output → goes into returns
    ]
    hdl.sub_modules['sub'] = ('sub', None, connections, None)

    ahdl_call = AHDL_MODULECALL(None, (AHDL_CONST(7),), 'sub', '', ())
    t = make_io_transformer(hdl)
    result = t.visit_AHDL_MODULECALL_SEQ(ahdl_call, 0, 2)

    # Should produce ready=1 + MOVE(acc_in=arg)
    assert isinstance(result, tuple)
    assert any(isinstance(s, AHDL_MOVE) for s in result)


# ============================================================
# WaitTransformer — _contains_meta_wait  (lines 98-104)
# ============================================================

def test_contains_meta_wait_direct():
    """An AHDL_META_WAIT itself returns True."""
    t = WaitTransformer()
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    assert t._contains_meta_wait(mw) is True


def test_contains_meta_wait_in_block():
    """A block containing META_WAIT returns True."""
    t = WaitTransformer()
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    block = AHDL_BLOCK('', (mw,))
    assert t._contains_meta_wait(block) is True


def test_contains_meta_wait_in_if():
    """An AHDL_IF whose block contains META_WAIT returns True."""
    t = WaitTransformer()
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    blk = AHDL_BLOCK('', (mw,))
    # Need a real condition expression for AHDL_IF
    cond = AHDL_CONST(1)
    ahdl_if = AHDL_IF((cond,), (blk,))
    assert t._contains_meta_wait(ahdl_if) is True


def test_contains_meta_wait_false():
    """A plain NOP returns False."""
    t = WaitTransformer()
    nop = AHDL_NOP('nothing')
    assert t._contains_meta_wait(nop) is False


def test_contains_meta_wait_block_without_wait():
    """A block with only NOP returns False."""
    t = WaitTransformer()
    nop = AHDL_NOP('x')
    block = AHDL_BLOCK('', (nop,))
    assert t._contains_meta_wait(block) is False


# ============================================================
# WaitTransformer — _partition_codes  (lines 137-146)
# ============================================================

def test_partition_codes_basic():
    """Partitions list around the delimiter object."""
    t = WaitTransformer()
    nop1 = AHDL_NOP('a')
    nop2 = AHDL_NOP('b')
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    codes = [nop1, mw, nop2]

    partitions = t._partition_codes(codes, mw)
    assert len(partitions) == 2
    assert partitions[0] == (nop1,)
    assert partitions[1] == (nop2,)


def test_partition_codes_delimiter_at_start():
    """Delimiter at position 0 → empty first partition."""
    t = WaitTransformer()
    nop = AHDL_NOP('b')
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    partitions = t._partition_codes([mw, nop], mw)
    assert partitions[0] == ()
    assert partitions[1] == (nop,)


def test_partition_codes_delimiter_at_end():
    """Delimiter at end → empty last partition."""
    t = WaitTransformer()
    nop = AHDL_NOP('a')
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    partitions = t._partition_codes([nop, mw], mw)
    assert partitions[0] == (nop,)
    assert partitions[1] == ()


# ============================================================
# WaitTransformer — _sink_trailing_codes_into_wait_if  (lines 107-126)
# ============================================================

def _make_cond_expr():
    return AHDL_CONST(1)


def test_sink_trailing_no_if():
    """A block with no AHDL_IF is returned unchanged."""
    t = WaitTransformer()
    nop = AHDL_NOP('x')
    block = AHDL_BLOCK('', (nop,))
    result = t._sink_trailing_codes_into_wait_if(block)
    assert result.codes == (nop,)


def test_sink_trailing_if_without_meta_wait():
    """An AHDL_IF without META_WAIT is not modified."""
    t = WaitTransformer()
    nop = AHDL_NOP('trailing')
    inner_nop = AHDL_NOP('inner')
    inner_blk = AHDL_BLOCK('', (inner_nop,))
    cond = _make_cond_expr()
    ahdl_if = AHDL_IF((cond,), (inner_blk,))
    block = AHDL_BLOCK('', (ahdl_if, nop))
    result = t._sink_trailing_codes_into_wait_if(block)
    # No change: trailing nop stays outside
    assert nop in result.codes


def test_sink_trailing_if_with_meta_wait_has_else():
    """Trailing codes after an AHDL_IF-with-wait are sunk; else branch is kept."""
    t = WaitTransformer()
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    trailing_nop = AHDL_NOP('trailing')
    inner_blk = AHDL_BLOCK('', (mw,))
    else_blk = AHDL_BLOCK('', (AHDL_NOP('else'),))
    cond = _make_cond_expr()
    # IF with explicit else (last cond is None)
    ahdl_if = AHDL_IF((cond, None), (inner_blk, else_blk))
    block = AHDL_BLOCK('', (ahdl_if, trailing_nop))

    result = t._sink_trailing_codes_into_wait_if(block)

    # The top-level block should now have only the new IF (trailing sunk in)
    assert len(result.codes) == 1
    new_if = result.codes[0]
    assert isinstance(new_if, AHDL_IF)
    # trailing_nop sunk into both branches
    for blk in new_if.blocks:
        assert trailing_nop in blk.codes


def test_sink_trailing_if_with_meta_wait_no_else():
    """When the IF has no else cond, an else branch containing trailing codes is added."""
    t = WaitTransformer()
    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    trailing_nop = AHDL_NOP('trailing')
    inner_blk = AHDL_BLOCK('', (mw,))
    cond = _make_cond_expr()
    # IF without else (only one condition, not None)
    ahdl_if = AHDL_IF((cond,), (inner_blk,))
    block = AHDL_BLOCK('', (ahdl_if, trailing_nop))

    result = t._sink_trailing_codes_into_wait_if(block)

    assert len(result.codes) == 1
    new_if = result.codes[0]
    assert isinstance(new_if, AHDL_IF)
    # An else branch (cond=None) must have been added
    assert new_if.conds[-1] is None
    # The new else block should contain the trailing nop
    else_blk = new_if.blocks[-1]
    assert trailing_nop in else_blk.codes


# ============================================================
# WaitTransformer — visit_AHDL_BLOCK  (lines 128-134)
# ============================================================

def test_visit_AHDL_BLOCK_no_meta_wait():
    """A block without META_WAIT is returned as-is (no _transform_meta_wait call)."""
    hdl = make_hdlmodule()
    t = make_wait_transformer(hdl)
    nop = AHDL_NOP('n')
    block = AHDL_BLOCK('', (nop,))
    result = t.visit_AHDL_BLOCK(block)
    assert isinstance(result, AHDL_BLOCK)
    assert all(not isinstance(c, AHDL_META_WAIT) for c in result.codes)


# ============================================================
# WaitTransformer — _build_waiting_state  (lines 149-159)
# ============================================================

def _make_stg_and_state(hdl, state_name='S0'):
    stg = STG('main', None, hdl)
    block = AHDL_BLOCK(state_name, ())
    state = stg.new_state(state_name, block, 0)
    stg.add_states([state])
    return stg, state


def test_build_waiting_state():
    """_build_waiting_state returns a new State with correct name and block structure."""
    hdl = make_hdlmodule()
    t = make_wait_transformer(hdl)
    stg, state = _make_stg_and_state(hdl, 'S0')
    t.current_state = state
    t.current_stg = stg

    cond = AHDL_CONST(1)
    next_codes = (AHDL_NOP('next'),)
    waiting = t._build_waiting_state(cond, next_codes)

    assert isinstance(waiting, State)
    assert waiting.name == 'S0_waiting0'
    assert waiting.step == state.step + 1
    assert waiting.stg is stg
    # Block should be an AHDL_BLOCK containing an AHDL_IF
    assert isinstance(waiting.block, AHDL_BLOCK)
    assert len(waiting.block.codes) == 1
    assert isinstance(waiting.block.codes[0], AHDL_IF)


def test_build_waiting_state_increments_count():
    """Each call to _build_waiting_state increments the counter."""
    hdl = make_hdlmodule()
    t = make_wait_transformer(hdl)
    stg, state = _make_stg_and_state(hdl, 'SX')
    t.current_state = state
    t.current_stg = stg

    cond = AHDL_CONST(1)
    w0 = t._build_waiting_state(cond, ())
    w1 = t._build_waiting_state(cond, ())
    assert w0.name == 'SX_waiting0'
    assert w1.name == 'SX_waiting1'


# ============================================================
# WaitTransformer — visit_State  (lines 90-95)
# ============================================================

def test_visit_State_no_additional():
    """A state whose block contains no META_WAIT is returned as a single State."""
    hdl = make_hdlmodule()
    t = make_wait_transformer(hdl)
    stg, state = _make_stg_and_state(hdl, 'Q0')
    t.current_stg = stg

    result = t.visit_State(state)

    assert isinstance(result, State)


def test_visit_State_with_meta_wait_produces_additional():
    """A state whose block contains META_WAIT produces a tuple of states."""
    hdl = make_hdlmodule()
    t = make_wait_transformer(hdl)
    stg = STG('main', None, hdl)
    t.current_stg = stg

    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    block = AHDL_BLOCK('W0', (mw,))
    state = State('W0', block, 0, stg)
    stg.add_states([state])

    result = t.visit_State(state)

    # Should be a tuple (original state + at least one waiting state)
    assert isinstance(result, tuple)
    assert len(result) >= 2
    for s in result:
        assert isinstance(s, State)


# ============================================================
# WaitTransformer — _transform_meta_wait  (lines 162-183)
# ============================================================

def test_transform_meta_wait_basic():
    """_transform_meta_wait replaces META_WAIT with AHDL_IF and appends waiting state."""
    hdl = make_hdlmodule()
    t = make_wait_transformer(hdl)
    stg, state = _make_stg_and_state(hdl, 'T0')
    t.current_state = state
    t.current_stg = stg
    t._additional_states = []

    mw = AHDL_META_WAIT('WAIT_COND', 'Eq', AHDL_CONST(1), AHDL_CONST(0))
    nop_after = AHDL_NOP('after')
    block = AHDL_BLOCK('T0', (mw, nop_after))

    result = t._transform_meta_wait(block, [mw])

    assert isinstance(result, AHDL_BLOCK)
    # The META_WAIT should have been replaced by an AHDL_IF
    assert not any(isinstance(c, AHDL_META_WAIT) for c in result.codes)
    assert any(isinstance(c, AHDL_IF) for c in result.codes)
    # A waiting state should have been appended
    assert len(t._additional_states) == 1
    assert isinstance(t._additional_states[0], State)
