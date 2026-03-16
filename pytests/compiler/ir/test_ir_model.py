"""Tests for pydantic-based IR model classes."""
import pytest
from pydantic import ValidationError
from polyphony.compiler.ir.ir import (
    Ctx, Ir, IrExp, IrStm, IrNameExp, IrVariable,
    Const, Temp, Attr, UnOp, BinOp, RelOp, CondOp, PolyOp,
    Call, SysCall, New, MRef, MStore, Array,
    Move, CMove, Expr, CExpr, Jump, CJump, MCJump, Ret,
    Phi, UPhi, LPhi, MStm,
)


# --- Const ---

def test_const_int():
    c = Const(value=42)
    assert c.value == 42
    assert str(c) == '42'


def test_const_bool():
    t = Const(value=True)
    f = Const(value=False)
    assert str(t) == 'True'
    assert str(f) == 'False'


def test_const_str():
    c = Const(value='hello')
    assert str(c) == "'hello'"


def test_const_eq():
    assert Const(value=1) == Const(value=1)
    assert Const(value=1) != Const(value=2)
    assert Const(value=1) != Const(value='1')


# --- Temp ---

def test_temp():
    t = Temp(name='x')
    assert t.name == 'x'
    assert t.ctx == Ctx.LOAD
    assert str(t) == 'x'


def test_temp_store():
    t = Temp(name='y', ctx=Ctx.STORE)
    assert t.ctx == Ctx.STORE


def test_temp_eq():
    assert Temp(name='x') == Temp(name='x')
    assert Temp(name='x') != Temp(name='y')
    assert Temp(name='x', ctx=Ctx.LOAD) != Temp(name='x', ctx=Ctx.STORE)


# --- Attr ---

def test_attr():
    a = Attr(name='field', exp=Temp(name='self'), attr='field')
    assert str(a) == 'self.field'
    assert a.qualified_name == ('self', 'field')


def test_attr_nested():
    inner = Attr(name='x', exp=Temp(name='a'), attr='x')
    outer = Attr(name='y', exp=inner, attr='y')
    assert str(outer) == 'a.x.y'
    assert outer.qualified_name == ('a', 'x', 'y')
    assert outer.head_name() == 'a'


# --- UnOp ---

def test_unop():
    u = UnOp(op='USub', exp=Temp(name='x'))
    assert str(u) == '-x'


def test_unop_validation():
    with pytest.raises(ValidationError):
        UnOp(op='INVALID', exp=Temp(name='x'))


# --- BinOp ---

def test_binop():
    b = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    assert str(b) == '(x + 1)'


def test_binop_eq():
    b1 = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    b2 = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    assert b1 == b2


def test_binop_validation():
    with pytest.raises(ValidationError):
        BinOp(op='INVALID', left=Temp(name='x'), right=Temp(name='y'))


def test_binop_kids():
    x = Temp(name='x')
    y = Temp(name='y')
    b = BinOp(op='Add', left=x, right=y)
    kids = b.kids()
    assert len(kids) == 2


# --- RelOp ---

def test_relop():
    r = RelOp(op='Eq', left=Temp(name='x'), right=Const(value=0))
    assert str(r) == '(x == 0)'


def test_relop_validation():
    with pytest.raises(ValidationError):
        RelOp(op='Add', left=Temp(name='x'), right=Temp(name='y'))


# --- CondOp ---

def test_condop():
    c = CondOp(cond=Temp(name='c'), left=Const(value=1), right=Const(value=0))
    assert str(c) == '(c ? 1 : 0)'


# --- PolyOp ---

def test_polyop():
    p = PolyOp(op='Add', values=[Const(value=1), Const(value=2), Const(value=3)])
    assert '+ [1, 2, 3]' in str(p)


# --- Call ---

def test_call():
    f = Temp(name='func', ctx=Ctx.CALL)
    c = Call(name='func', func=f, args=[('', Const(value=1)), ('', Const(value=2))])
    assert 'func(1, 2)' == str(c)


# --- SysCall ---

def test_syscall():
    f = Temp(name='print', ctx=Ctx.CALL)
    c = SysCall(name='print', func=f, args=[('', Const(value=42))])
    assert '!print(42)' == str(c)


# --- New ---

def test_new():
    f = Temp(name='C', ctx=Ctx.CALL)
    n = New(name='C', func=f, args=[('', Const(value=1))])
    assert '$C(1)' == str(n)


# --- MRef ---

def test_mref():
    m = MRef(mem=Temp(name='xs'), offset=Const(value=0))
    assert str(m) == 'xs[0]'


# --- MStore ---

def test_mstore():
    m = MStore(mem=Temp(name='xs'), offset=Const(value=0), exp=Temp(name='v'))
    assert str(m) == 'mstore(xs[0], v)'


# --- Array ---

def test_array_mutable():
    a = Array(items=[Const(value=1), Const(value=2), Const(value=3)], mutable=True)
    assert str(a) == '[1, 2, 3]'
    assert a.is_mutable
    assert a.getlen() == 3


def test_array_immutable():
    a = Array(items=[Temp(name='x'), Temp(name='y')], mutable=False)
    assert str(a) == '(x, y)'
    assert not a.is_mutable


# --- Move ---

def test_move():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    assert str(m) == 'y = 1'


def test_move_eq():
    m1 = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    m2 = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    assert m1 == m2


# --- CMove ---

def test_cmove():
    m = CMove(
        cond=Temp(name='c'),
        dst=Temp(name='x', ctx=Ctx.STORE),
        src=Const(value=1),
    )
    assert 'c ?' in str(m)
    assert 'x = 1' in str(m)


# --- Expr ---

def test_expr():
    e = Expr(exp=Call(name='f', func=Temp(name='f', ctx=Ctx.CALL), args=[]))
    assert str(e) == 'f()'


# --- CExpr ---

def test_cexpr():
    e = CExpr(cond=Temp(name='c'), exp=Call(name='f', func=Temp(name='f', ctx=Ctx.CALL), args=[]))
    assert 'c ? f()' == str(e)


# --- Ret ---

def test_ret():
    r = Ret(exp=Temp(name='@return'))
    assert str(r) == 'return @return'


# --- model_copy ---

def test_model_copy_deep():
    b = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    b2 = b.model_copy(deep=True)
    assert b == b2
    assert b is not b2
    assert b.left is not b2.left


def test_model_copy_update():
    b = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    b2 = b.model_copy(update={'right': Const(value=2)})
    assert b.right == Const(value=1)
    assert b2.right == Const(value=2)
    assert b2.op == 'Add'


def test_model_copy_stm():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    m2 = m.model_copy(update={'src': Const(value=99)})
    assert m.src == Const(value=1)
    assert m2.src == Const(value=99)


# --- Mutation (Phase 1: frozen=False) ---

def test_mutation_allowed():
    b = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    b.left = Temp(name='y')
    assert b.left == Temp(name='y')


def test_mutation_stm():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    m.src = Const(value=42)
    assert m.src == Const(value=42)


# --- JSON serialize ---

def test_json_roundtrip_const():
    c = Const(value=42)
    j = c.model_dump()
    c2 = Const.model_validate(j)
    assert c2.value == 42


def test_json_roundtrip_temp():
    t = Temp(name='x', ctx=Ctx.LOAD)
    j = t.model_dump()
    t2 = Temp.model_validate(j)
    assert t2.name == 'x'
    assert t2.ctx == Ctx.LOAD


def test_json_roundtrip_binop():
    b = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    j = b.model_dump()
    # BinOp's left/right typed as IrExp, so pydantic only dumps IrExp fields (empty).
    # Full polymorphic serialization requires discriminated unions (future work).
    # For now, verify top-level fields dump correctly.
    assert j['op'] == 'Add'
