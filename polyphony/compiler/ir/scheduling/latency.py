from ..ir import *
from ..irhelper import qualified_symbols
from ..symbol import Symbol
from ...common.env import env

UNIT_STEP = 1
CALL_MINIMUM_STEP = 3


def get_call_latency(call, stm, scope):
    # FIXME: It is better to ask HDLInterface the I/O latency
    is_pipelined = stm.block.synth_params['scheduling'] == 'pipeline'
    callee_scope = call.get_callee_scope(scope)
    # callee_scope = call.callee_scope
    if callee_scope.is_method() and callee_scope.parent.is_port():
        qsym = qualified_symbols(call.func, scope)
        receiver = qsym[-2]
        assert isinstance(receiver, Symbol)
        assert receiver.typ.is_port()
        if callee_scope.base_name == 'rd':
            dummy_read = stm.is_a(EXPR)
            if dummy_read:
                return 0
            else:
                return UNIT_STEP * 1
        return UNIT_STEP
    elif callee_scope.parent.name.startswith('polyphony.Net'):
        if callee_scope.base_name == 'rd':
            if stm.is_a(MOVE):
                if stm.dst.symbol.is_alias():
                    return 0
                else:
                    return UNIT_STEP * 1
            else:
                return 0
    elif callee_scope.asap_latency > 0:
        return UNIT_STEP * callee_scope.asap_latency
    return UNIT_STEP * CALL_MINIMUM_STEP


def get_syscall_latency(call):
    if call.name == 'polyphony.timing.clksleep':
        _, cycle = call.args[0]
        if cycle.is_a(CONST) and cycle.value <= env.sleep_sentinel_thredhold:
            return cycle.value
        else:
            return 1
    elif call.name.startswith('polyphony.timing.wait_'):
        return 0
    if call.name in ('assert', 'print'):
        return 0
    return UNIT_STEP


def _get_latency(tag):
    assert isinstance(tag, IRStm)
    scope = cast(IRStm, tag).block.scope
    if tag.is_a(MOVE):
        move = cast(MOVE, tag)
        dst_sym = qualified_symbols(move.dst, scope)[-1]
        assert isinstance(dst_sym, Symbol)
        if move.dst.is_a(TEMP) and dst_sym.is_alias():
            return 0
        elif move.src.is_a(CALL):
            return get_call_latency(move.src, move, scope)
        elif move.src.is_a(NEW):
            return 0
        elif move.src.is_a(TEMP) and scope.find_sym(move.src.name).typ.is_port():
            return 0
        elif move.dst.is_a(ATTR):
            if dst_sym.is_alias():
                return 0
            return UNIT_STEP * 1
        elif move.src.is_a(MREF):
            return UNIT_STEP
        elif move.dst.is_a(TEMP) and dst_sym.typ.is_seq():
            if move.src.is_a(ARRAY):
                return UNIT_STEP
        if dst_sym.is_alias():
            return 0
    elif tag.is_a(EXPR):
        expr = cast(EXPR, tag)
        if expr.exp.is_a(CALL):
            return get_call_latency(expr.exp, tag, scope)
        elif expr.exp.is_a(SYSCALL):
            return get_syscall_latency(expr.exp)
        elif expr.exp.is_a(MSTORE):
            return UNIT_STEP
    elif tag.is_a(PHI):
        phi = cast(PHI, tag)
        var_sym = qualified_symbols(phi.var, scope)[-1]
        assert isinstance(var_sym, Symbol)
        if var_sym.is_alias():
            return 0
    elif tag.is_a(UPHI):
        uphi = cast(UPHI, tag)
        var_sym = qualified_symbols(uphi.var, scope)[-1]
        assert isinstance(var_sym, Symbol)
        if var_sym.is_alias():
            return 0
    return UNIT_STEP


def get_latency(tag):
    l = _get_latency(tag)
    if isinstance(l, tuple):
        return l[0], l[1]
    else:
        return l, l
