"""Latency calculation for IR statements."""

from typing import cast
from ..ir import (
    Move,
    Expr,
    Const,
    Temp,
    Attr,
    Call,
    SysCall,
    New,
    Array,
    MRef,
    MStore,
    IrStm,
    Phi,
    UPhi,
    IrVariable,
)
from ..irhelper import qualified_symbols
from ..symbol import Symbol
from ...common.env import env

UNIT_STEP = 1
CALL_MINIMUM_STEP = 3


def _get_call_latency(call, stm, scope):
    """Calculate latency for a call statement."""
    if stm.block:
        stm_blk = scope.find_block(stm.block)
    else:
        stm_blk = next((b for b in scope.traverse_blocks() if stm in b.stms), None)
    is_pipelined = stm_blk and stm_blk.synth_params["scheduling"] == "pipeline"
    callee_scope = call.get_callee_scope(scope)
    if callee_scope.is_method() and callee_scope.parent.is_port():
        qsym = qualified_symbols(call.func, scope)
        receiver = qsym[-2]
        assert isinstance(receiver, Symbol)
        assert receiver.typ.is_port()
        if callee_scope.base_name == "rd":
            dummy_read = isinstance(stm, Expr)
            if dummy_read:
                return 0
            else:
                return UNIT_STEP * 1
        return UNIT_STEP
    elif callee_scope.parent.name.startswith("polyphony.Net"):
        if callee_scope.base_name == "rd":
            if isinstance(stm, Move):
                dst_sym = qualified_symbols(stm.dst, scope)[-1]
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
    if name == "polyphony.timing.clksleep":
        _, cycle = call.args[0]
        if isinstance(cycle, Const) and cycle.value <= env.sleep_sentinel_thredhold:
            return cycle.value
        else:
            return 1
    elif name.startswith("polyphony.timing.wait_"):
        return 0
    if name in ("assert", "print"):
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
    if isinstance(tag, Move):
        move_tag = cast(Move, tag)
        dst_sym = qualified_symbols(move_tag.dst, scope)[-1]
        assert isinstance(dst_sym, Symbol)
        if isinstance(move_tag.dst, Temp) and dst_sym.is_alias():
            return 0
        elif isinstance(move_tag.src, Call):
            return _get_call_latency(move_tag.src, move_tag, scope)
        elif isinstance(move_tag.src, New):
            return 0
        elif (
            isinstance(move_tag.src, Temp)
            and (src_sym := scope.find_sym(cast(Temp, move_tag.src).name))
            and src_sym.typ.is_port()
        ):
            return 0
        elif isinstance(move_tag.dst, Attr):
            if dst_sym.is_alias():
                return 0
            return UNIT_STEP * 1
        elif isinstance(move_tag.src, MRef):
            return UNIT_STEP
        elif isinstance(move_tag.dst, Temp) and dst_sym.typ.is_seq():
            if isinstance(move_tag.src, Array):
                return UNIT_STEP
        if dst_sym.is_alias():
            return 0
    elif isinstance(tag, Expr):
        expr_tag = cast(Expr, tag)
        exp = expr_tag.exp
        if isinstance(exp, Call):
            return _get_call_latency(exp, tag, scope)
        elif isinstance(exp, SysCall):
            return _get_syscall_latency(exp)
        elif isinstance(exp, MStore):
            return UNIT_STEP
    elif isinstance(tag, Phi):
        var_sym = qualified_symbols(tag.var, scope)[-1]
        assert isinstance(var_sym, Symbol)
        if var_sym.is_alias():
            return 0
    elif isinstance(tag, UPhi):
        var_sym = qualified_symbols(tag.var, scope)[-1]
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
