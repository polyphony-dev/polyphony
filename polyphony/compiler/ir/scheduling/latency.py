"""Latency calculation for IR statements."""
from typing import cast
from ..ir import (
    Move, Expr, Const, Temp, Attr, Call, SysCall, New, Array,
    MRef, MStore, IrStm, Phi, UPhi, IrVariable,
)
from ..irhelper import qualified_symbols
from ..symbol import Symbol
from ...common.env import env
from .dataflow import (
    _is_move, _is_expr, _is_const, _is_temp, _is_attr,
    _is_call, _is_syscall, _is_new, _is_array, _is_mref,
    _is_mstore, _qualified_symbols,
)

UNIT_STEP = 1
CALL_MINIMUM_STEP = 3


def _get_call_latency(call, stm, scope):
    """Calculate latency for a call statement."""
    if stm.block:
        stm_blk = scope.find_block(stm.block)
    else:
        stm_blk = next((b for b in scope.traverse_blocks() if stm in b.stms), None)
    is_pipelined = stm_blk and stm_blk.synth_params['scheduling'] == 'pipeline'
    callee_scope = call.get_callee_scope(scope)
    if callee_scope.is_method() and callee_scope.parent.is_port():
        qsym = _qualified_symbols(call.func, scope)
        receiver = qsym[-2]
        assert isinstance(receiver, Symbol)
        assert receiver.typ.is_port()
        if callee_scope.base_name == 'rd':
            dummy_read = _is_expr(stm)
            if dummy_read:
                return 0
            else:
                return UNIT_STEP * 1
        return UNIT_STEP
    elif callee_scope.parent.name.startswith('polyphony.Net'):
        if callee_scope.base_name == 'rd':
            if _is_move(stm):
                dst_sym = _qualified_symbols(stm.dst, scope)[-1]
                if isinstance(dst_sym, Symbol) and dst_sym.is_alias():
                    return 0
                else:
                    return UNIT_STEP * 1
            else:
                return 0
    elif callee_scope.asap_latency > 0:
        return UNIT_STEP * callee_scope.asap_latency
    return UNIT_STEP * CALL_MINIMUM_STEP


def _get_syscall_latency(call):
    """Calculate latency for a syscall."""
    name = call.name
    if name == 'polyphony.timing.clksleep':
        _, cycle = call.args[0]
        if _is_const(cycle) and cycle.value <= env.sleep_sentinel_thredhold:
            return cycle.value
        else:
            return 1
    elif name.startswith('polyphony.timing.wait_'):
        return 0
    if name in ('assert', 'print'):
        return 0
    return UNIT_STEP


def _get_latency(tag, scope=None):
    """Calculate latency for a statement (handles both old and new IR)."""
    assert isinstance(tag, IrStm)
    if scope is None:
        from ...common.env import env
        if tag.block:
            for s in env.scopes.values():
                if tag.block in s.block_map:
                    blk = s.block_map[tag.block]
                    if tag in blk.stms:
                        scope = s
                        break

    assert scope is not None
    if _is_move(tag):
        move_tag = cast(Move, tag)
        dst_sym = _qualified_symbols(move_tag.dst, scope)[-1]
        assert isinstance(dst_sym, Symbol)
        if _is_temp(move_tag.dst) and dst_sym.is_alias():
            return 0
        elif _is_call(move_tag.src):
            return _get_call_latency(move_tag.src, move_tag, scope)
        elif _is_new(move_tag.src):
            return 0
        elif _is_temp(move_tag.src) and (src_sym := scope.find_sym(cast(Temp, move_tag.src).name)) and src_sym.typ.is_port():
            return 0
        elif _is_attr(move_tag.dst):
            if dst_sym.is_alias():
                return 0
            return UNIT_STEP * 1
        elif _is_mref(move_tag.src):
            return UNIT_STEP
        elif _is_temp(move_tag.dst) and dst_sym.typ.is_seq():
            if _is_array(move_tag.src):
                return UNIT_STEP
        if dst_sym.is_alias():
            return 0
    elif _is_expr(tag):
        expr_tag = cast(Expr, tag)
        exp = expr_tag.exp
        if _is_call(exp):
            return _get_call_latency(exp, tag, scope)
        elif _is_syscall(exp):
            return _get_syscall_latency(exp)
        elif _is_mstore(exp):
            return UNIT_STEP
    elif isinstance(tag, Phi):
        var_sym = _qualified_symbols(tag.var, scope)[-1]
        assert isinstance(var_sym, Symbol)
        if var_sym.is_alias():
            return 0
    elif isinstance(tag, UPhi):
        var_sym = _qualified_symbols(tag.var, scope)[-1]
        assert isinstance(var_sym, Symbol)
        if var_sym.is_alias():
            return 0
    return UNIT_STEP


def get_latency(tag, scope=None):
    """Get (def_latency, seq_latency) for a statement."""
    l = _get_latency(tag, scope)
    if isinstance(l, tuple):
        return l[0], l[1]
    else:
        return l, l
