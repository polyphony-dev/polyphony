"""Tests for VarReplacer, especially ExprType.expr handling."""
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.ir import Temp, Const, Ctx, Expr
from polyphony.compiler.ir.transformers.varreplacer import VarReplacer
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.types.exprtype import ExprType
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_visit_with_context_new_ir_expr():
    """VarReplacer.visit_with_context handles new IR Expr nodes
    directly since ExprType.expr now holds new IR Expr."""
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(8))
    scope.add_sym('y', tags=set(), typ=Type.int(8))

    # Create new IR Expr containing Temp('x')
    new_expr = Expr(exp=Temp(name='x'))

    # Create VarReplacer to replace x -> Const(5)
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit_with_context(scope, new_expr)

    # The new IR Expr should have x replaced with Const(5)
    assert isinstance(new_expr.exp, new.Const)
    assert new_expr.exp.value == 5


def test_visit_with_context_new_ir():
    """VarReplacer.visit_with_context should handle new IR stms normally."""
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(8))

    new_expr = new.Expr(exp=new.Temp(name='x'))
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit_with_context(scope, new_expr)

    assert isinstance(new_expr.exp, new.Const)
    assert new_expr.exp.value == 5
