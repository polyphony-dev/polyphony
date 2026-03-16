"""Tests for ExprType holding new IR Expr nodes."""
from polyphony.compiler.ir.ir import Expr, Temp, Const, BinOp, Attr, Ctx
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.types.exprtype import ExprType
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def _get_scope():
    """Get a scope for testing from the existing builtin scopes."""
    return env.scopes['__builtin__']


def test_exprtype_holds_new_ir_expr():
    """ExprType.expr should hold a new IR Expr node."""
    setup_test()
    scope = _get_scope()
    expr_node = Expr(exp=Temp(name='x', ctx=Ctx.LOAD))
    t = Type.expr(expr_node, scope)
    assert isinstance(t, ExprType)
    assert isinstance(t.expr, Expr)
    assert t.expr.exp.name == 'x'


def test_exprtype_str():
    """ExprType.__str__ should work with new IR Expr."""
    setup_test()
    scope = _get_scope()
    expr_node = Expr(exp=Const(value=42))
    t = Type.expr(expr_node, scope)
    s = str(t)
    assert 'expr' in s


def test_exprtype_find_irs():
    """Expr.find_irs should work on ExprType.expr."""
    setup_test()
    scope = _get_scope()
    from polyphony.compiler.ir.ir import IrVariable
    inner = BinOp(op='Add', left=Temp(name='a', ctx=Ctx.LOAD), right=Temp(name='b', ctx=Ctx.LOAD))
    expr_node = Expr(exp=inner)
    t = Type.expr(expr_node, scope)
    vs = t.expr.find_irs(IrVariable)
    assert len(vs) == 2
    names = {v.name for v in vs}
    assert names == {'a', 'b'}


def test_exprtype_mangled_name():
    """Type.mangled_names should work with new IR Expr in ExprType."""
    setup_test()
    scope = _get_scope()
    expr_node = Expr(exp=Temp(name='x', ctx=Ctx.LOAD))
    t = Type.expr(expr_node, scope)
    name = Type.mangled_names([t])
    assert isinstance(name, str)
    assert len(name) > 0
