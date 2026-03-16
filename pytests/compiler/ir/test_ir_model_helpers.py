"""Tests for new IR helper methods and ir_helper.py functions."""
from polyphony.compiler.ir.ir import (
    Ctx, Ir, IrExp, IrStm, IrVariable, IrNameExp,
    Const, Temp, Attr, UnOp, BinOp, RelOp, CondOp,
    Call, SysCall, New, MRef, MStore, Array,
    Move, Expr, CJump, Jump, Ret,
)
from polyphony.compiler.ir.ir_helper import (
    qualified_symbols, irexp_type, reduce_relexp, reduce_binop, qsym2var,
)
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Ir.find_irs tests
# ============================================================

def test_find_irs_simple():
    b = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    temps = b.find_irs(Temp)
    assert len(temps) == 1
    assert temps[0].name == 'x'


def test_find_irs_nested():
    b = BinOp(op='Add',
              left=BinOp(op='Mult', left=Temp(name='a'), right=Temp(name='b')),
              right=Const(value=1))
    temps = b.find_irs(Temp)
    assert len(temps) == 2
    names = {t.name for t in temps}
    assert names == {'a', 'b'}


def test_find_irs_in_call():
    c = Call(name='f', func=Temp(name='f', ctx=Ctx.CALL),
             args=[('', Temp(name='a')), ('', Const(value=1))])
    temps = c.find_irs(Temp)
    assert len(temps) == 2
    names = {t.name for t in temps}
    assert names == {'f', 'a'}


def test_find_irs_in_move():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE),
             src=BinOp(op='Add', left=Temp(name='x'), right=Const(value=2)))
    vars = m.find_irs(IrVariable)
    assert len(vars) == 2
    names = {v.name for v in vars}
    assert names == {'y', 'x'}


def test_find_irs_consts():
    b = BinOp(op='Add', left=Const(value=1), right=Const(value=2))
    consts = b.find_irs(Const)
    assert len(consts) == 2


def test_find_irs_empty():
    c = Const(value=42)
    temps = c.find_irs(Temp)
    assert temps == []


def test_find_irs_mref():
    m = MRef(mem=Temp(name='xs'), offset=Temp(name='i'))
    temps = m.find_irs(Temp)
    assert len(temps) == 2


def test_find_irs_array():
    a = Array(items=[Temp(name='a'), Const(value=1), Temp(name='b')])
    temps = a.find_irs(Temp)
    assert len(temps) == 2


def test_find_irs_attr():
    attr = Attr(name='field', exp=Temp(name='self'), attr='field')
    temps = attr.find_irs(Temp)
    assert len(temps) == 1
    assert temps[0].name == 'self'


# ============================================================
# ir_helper.qualified_symbols tests
# ============================================================

def test_qualified_symbols_temp():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(8))

    t = Temp(name='x')
    qsyms = qualified_symbols(t, scope)
    assert len(qsyms) == 1
    assert isinstance(qsyms[0], Symbol)
    assert qsyms[0].name == 'x'


def test_qualified_symbols_attr():
    setup_test()
    X = Scope.create(None, 'X', {'class'}, 0)
    X.add_sym('value', tags=set(), typ=Type.int(8))
    Y = Scope.create(None, 'Y', {'class'}, 0)
    Y.add_sym('x', tags=set(), typ=Type.object(X))

    a = Attr(name='value', exp=Temp(name='x'), attr='value')
    qsyms = qualified_symbols(a, Y)
    assert len(qsyms) == 2
    assert qsyms[0].name == 'x'
    assert qsyms[1].name == 'value'


# ============================================================
# ir_helper.reduce_relexp tests
# ============================================================

def test_reduce_relexp_and_true():
    # True AND x => x
    exp = RelOp(op='And', left=Const(value=1), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_relexp_and_false():
    # False AND x => 0
    exp = RelOp(op='And', left=Const(value=0), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 0


def test_reduce_relexp_or_true():
    # True OR x => 1
    exp = RelOp(op='Or', left=Const(value=1), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 1


def test_reduce_relexp_or_false():
    # False OR x => x
    exp = RelOp(op='Or', left=Const(value=0), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_relexp_not_const():
    # NOT True => 0
    exp = UnOp(op='Not', exp=Const(value=1))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 0


def test_reduce_relexp_not_const_false():
    # NOT False => 1
    exp = UnOp(op='Not', exp=Const(value=0))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 1


def test_reduce_relexp_passthrough():
    # x AND y => unchanged
    exp = RelOp(op='And', left=Temp(name='x'), right=Temp(name='y'))
    result = reduce_relexp(exp)
    assert isinstance(result, RelOp)


# ============================================================
# ir_helper.reduce_binop tests
# ============================================================

def test_reduce_binop_add_zero():
    b = BinOp(op='Add', left=Const(value=0), right=Temp(name='x'))
    result = reduce_binop(b)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_binop_mult_one():
    b = BinOp(op='Mult', left=Temp(name='x'), right=Const(value=1))
    result = reduce_binop(b)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_binop_mult_zero():
    b = BinOp(op='Mult', left=Temp(name='x'), right=Const(value=0))
    result = reduce_binop(b)
    assert isinstance(result, Const)
    assert result.value == 0


def test_reduce_binop_passthrough():
    b = BinOp(op='Add', left=Temp(name='x'), right=Temp(name='y'))
    result = reduce_binop(b)
    assert isinstance(result, BinOp)


# ============================================================
# ir_helper.irexp_type tests
# ============================================================

def test_irexp_type_const():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    t = irexp_type(Const(value=42), scope)
    assert t.is_int()


def test_irexp_type_temp():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(16))
    t = irexp_type(Temp(name='x'), scope)
    assert t.is_int()
    assert t.width == 16


def test_irexp_type_relop():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    t = irexp_type(RelOp(op='Eq', left=Temp(name='x'), right=Const(value=0)), scope)
    assert t.is_bool()


def test_irexp_type_array():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    a = Array(items=[Const(value=1), Const(value=2)], mutable=True)
    t = irexp_type(a, scope)
    assert t.is_list()
    assert t.length == 2


# ============================================================
# Ir.find_vars tests
# ============================================================

def test_find_vars_temp():
    m = Move(dst=Temp(name='x', ctx=Ctx.STORE),
             src=BinOp(op='Add', left=Temp(name='x'), right=Const(value=1)))
    vars = m.find_vars(('x',))
    assert len(vars) == 2
    assert all(v.name == 'x' for v in vars)


def test_find_vars_attr():
    m = Move(dst=Attr(name='field', exp=Temp(name='self'), attr='field', ctx=Ctx.STORE),
             src=Attr(name='field', exp=Temp(name='self'), attr='field'))
    vars = m.find_vars(('self', 'field'))
    assert len(vars) == 2


def test_find_vars_not_found():
    m = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
    vars = m.find_vars(('y',))
    assert len(vars) == 0


def test_find_vars_in_call():
    c = Call(name='f', func=Temp(name='f', ctx=Ctx.CALL),
             args=[('', Temp(name='x')), ('', Temp(name='y'))])
    vars = c.find_vars(('x',))
    assert len(vars) == 1


# ============================================================
# Ir.replace tests (including tuple traversal)
# ============================================================

def test_replace_simple_temp():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE),
             src=BinOp(op='Add', left=Temp(name='x'), right=Const(value=1)))
    m.replace(Temp(name='x'), Temp(name='z'))
    assert m.src.left.name == 'z'


def test_replace_in_syscall_args():
    """SysCall.args is list[tuple[str, IrExp]]. The replace method must
    traverse tuples inside lists to find and replace variables."""
    f = Temp(name='len', ctx=Ctx.CALL)
    sc = SysCall(name='len', func=f, args=[('', Temp(name='d'))])
    m = Move(dst=Temp(name='r', ctx=Ctx.STORE), src=sc)
    m.replace(Temp(name='d'), Temp(name='data0'))
    _, arg = m.src.args[0]
    assert arg.name == 'data0'


def test_replace_in_call_args():
    """Call.args is list[tuple[str, IrExp]]. Same tuple traversal needed."""
    f = Temp(name='func', ctx=Ctx.CALL)
    c = Call(name='func', func=f, args=[('x', Temp(name='a')), ('y', Const(value=1))])
    c.replace(Temp(name='a'), Temp(name='b'))
    _, arg = c.args[0]
    assert arg.name == 'b'


def test_replace_in_nested_call_args():
    """Replace inside nested expression within tuple args."""
    f = Temp(name='f', ctx=Ctx.CALL)
    inner = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    c = Call(name='f', func=f, args=[('', inner)])
    c.replace(Temp(name='x'), Temp(name='y'))
    _, arg = c.args[0]
    assert isinstance(arg, BinOp)
    assert arg.left.name == 'y'


def test_replace_no_match():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    result = m.replace(Temp(name='z'), Temp(name='w'))
    assert not result
    assert m.src == Const(value=1)


# ============================================================
# ir_helper.qsym2var tests
# ============================================================

def test_qsym2var_single():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    sym = scope.add_sym('x', tags=set(), typ=Type.int(8))
    var = qsym2var((sym,), Ctx.LOAD)
    assert isinstance(var, Temp)
    assert var.name == 'x'
    assert var.ctx == Ctx.LOAD


def test_qsym2var_nested():
    setup_test()
    X = Scope.create(None, 'X', {'class'}, 0)
    x_sym = X.add_sym('value', tags=set(), typ=Type.int(8))
    Y = Scope.create(None, 'Y', {'class'}, 0)
    y_sym = Y.add_sym('x', tags=set(), typ=Type.object(X))

    var = qsym2var((y_sym, x_sym), Ctx.STORE)
    assert isinstance(var, Attr)
    assert var.name == 'value'
    assert var.ctx == Ctx.STORE
    assert var.exp.name == 'x'
