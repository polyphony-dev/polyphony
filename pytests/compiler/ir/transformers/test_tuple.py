"""Tests for TupleTransformer."""
from polyphony.compiler.ir.ir import (
    Array, Const, Ctx, Move, MRef, Ret, Temp, Call,
)
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.tuple import TupleTransformer
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def _make_scope(tags=None):
    if tags is None:
        tags = {'function', 'returnable'}
    setup_test()
    scope = Scope.create(None, 'TupleTest', tags, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    return scope


def _build_and_run(scope, stms):
    """Build a block with stms, run TupleTransformer, return resulting stms."""
    blk = Block(scope, nametag='entry')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)
    for stm in stms:
        blk.append_stm(stm)
    blk.append_stm(Ret(Temp('@return')))
    t = TupleTransformer()
    t.process(scope)
    # Return stms excluding the Ret at the end
    return blk.stms[:-1]


# ============================================================
# _can_direct_unpack
# ============================================================

def test_can_direct_unpack_no_overlap():
    """No overlap between lhs and rhs -> True."""
    scope = _make_scope()
    t = TupleTransformer()
    t.scope = scope
    lhs = [Temp('a', Ctx.STORE), Temp('b', Ctx.STORE)]
    rhs = [Temp('c'), Temp('d')]
    assert t._can_direct_unpack(lhs, rhs) is True


def test_can_direct_unpack_with_overlap():
    """lhs[0] name appears in rhs[1:] -> False."""
    scope = _make_scope()
    t = TupleTransformer()
    t.scope = scope
    # a = b, b = a  -- 'a' appears in rhs[1:] (which is [Temp('a')])
    lhs = [Temp('a', Ctx.STORE), Temp('b', Ctx.STORE)]
    rhs = [Temp('b'), Temp('a')]
    assert t._can_direct_unpack(lhs, rhs) is False


def test_can_direct_unpack_with_const():
    """Const items are not IrVariable, so is_contain returns False -> True."""
    scope = _make_scope()
    t = TupleTransformer()
    t.scope = scope
    lhs = [Const(value=1), Const(value=2)]
    rhs = [Const(value=3), Const(value=4)]
    assert t._can_direct_unpack(lhs, rhs) is True


# ============================================================
# _unpack
# ============================================================

def test_unpack_basic():
    """_unpack produces Move(dst, src) pairs."""
    scope = _make_scope()
    t = TupleTransformer()
    t.scope = scope
    lhs = [Temp('a', Ctx.STORE), Temp('b', Ctx.STORE)]
    rhs = [Temp('x'), Temp('y')]
    mvs = t._unpack(lhs, rhs)
    assert len(mvs) == 2
    assert all(isinstance(m, Move) for m in mvs)
    assert mvs[0].dst.name == 'a'
    assert mvs[0].src.name == 'x'
    assert mvs[1].dst.name == 'b'
    assert mvs[1].src.name == 'y'


# ============================================================
# visit_Move: Array dst + Array src (direct unpack)
# ============================================================

def test_visit_move_array_direct_unpack():
    """Array dst + Array src with no overlap -> direct unpack into individual Moves."""
    scope = _make_scope()
    scope.add_sym('a', tags=set(), typ=Type.int(32))
    scope.add_sym('b', tags=set(), typ=Type.int(32))
    scope.add_sym('x', tags=set(), typ=Type.int(32))
    scope.add_sym('y', tags=set(), typ=Type.int(32))

    dst = Array(items=[Temp('a', Ctx.STORE), Temp('b', Ctx.STORE)], mutable=False)
    src = Array(items=[Temp('x'), Temp('y')], mutable=False)
    mv = Move(dst=dst, src=src)

    result = _build_and_run(scope, [mv])
    assert len(result) == 2
    assert all(isinstance(s, Move) for s in result)
    assert result[0].dst.name == 'a'
    assert result[0].src.name == 'x'
    assert result[1].dst.name == 'b'
    assert result[1].src.name == 'y'


# ============================================================
# visit_Move: Array dst + Array src (indirect unpack with temps)
# ============================================================

def test_visit_move_array_indirect_unpack():
    """Array dst + Array src with overlap -> temp-based unpack."""
    scope = _make_scope()
    scope.add_sym('a', tags=set(), typ=Type.int(32))
    scope.add_sym('b', tags=set(), typ=Type.int(32))

    # a, b = b, a  -- overlap: 'a' appears in rhs[1:]
    dst = Array(items=[Temp('a', Ctx.STORE), Temp('b', Ctx.STORE)], mutable=False)
    src = Array(items=[Temp('b'), Temp('a')], mutable=False)
    mv = Move(dst=dst, src=src)

    result = _build_and_run(scope, [mv])
    # Should have 4 moves: 2 to temps, 2 from temps to destinations
    assert len(result) == 4
    assert all(isinstance(s, Move) for s in result)
    # First two moves store rhs into temps
    temp_names = [result[0].dst.name, result[1].dst.name]
    assert all('@t' in n for n in temp_names)
    # Last two moves load from temps into final destinations
    assert result[2].dst.name == 'a'
    assert result[3].dst.name == 'b'


# ============================================================
# visit_Move: non-Array dst (passthrough)
# ============================================================

def test_visit_move_passthrough():
    """Non-Array dst passes through with visit on src and dst."""
    scope = _make_scope()
    scope.add_sym('x', tags=set(), typ=Type.int(32))
    scope.add_sym('y', tags=set(), typ=Type.int(32))

    mv = Move(dst=Temp('x', Ctx.STORE), src=Temp('y'))
    result = _build_and_run(scope, [mv])
    assert len(result) == 1
    assert isinstance(result[0], Move)
    assert result[0].dst.name == 'x'
    assert result[0].src.name == 'y'


# ============================================================
# visit_Move: Array dst + IrVariable src of tuple type (MRef path)
# ============================================================

def test_visit_move_tuple_var_unpack():
    """Array dst + Temp src with tuple type -> MRef unpack."""
    scope = _make_scope()
    scope.add_sym('a', tags=set(), typ=Type.int(32))
    scope.add_sym('b', tags=set(), typ=Type.int(32))
    scope.add_sym('tup', tags=set(), typ=Type.tuple(Type.int(32), 2))

    dst = Array(items=[Temp('a', Ctx.STORE), Temp('b', Ctx.STORE)], mutable=False)
    src = Temp('tup')
    mv = Move(dst=dst, src=src)

    result = _build_and_run(scope, [mv])
    assert len(result) == 2
    assert all(isinstance(s, Move) for s in result)
    # src of each move should be MRef
    assert isinstance(result[0].src, MRef)
    assert isinstance(result[1].src, MRef)
    # Offsets should be 0 and 1
    assert result[0].src.offset.value == 0
    assert result[1].src.offset.value == 1
    # Destinations should be a and b
    assert result[0].dst.name == 'a'
    assert result[1].dst.name == 'b'


# ============================================================
# visit_Move: Array dst + Call src in testbench -> NotImplementedError
# ============================================================

def test_visit_move_call_in_testbench_raises():
    """Array dst + Call src in testbench scope raises NotImplementedError."""
    scope = _make_scope(tags={'function', 'returnable', 'testbench'})
    scope.add_sym('a', tags=set(), typ=Type.int(32))
    scope.add_sym('b', tags=set(), typ=Type.int(32))
    scope.add_sym('f', tags=set(), typ=Type.int(32))

    dst = Array(items=[Temp('a', Ctx.STORE), Temp('b', Ctx.STORE)], mutable=False)
    src = Call(func=Temp('f', Ctx.CALL), args=[], kwargs={})
    mv = Move(dst=dst, src=src)

    import pytest
    with pytest.raises(NotImplementedError, match='Return of sequence type value'):
        _build_and_run(scope, [mv])
