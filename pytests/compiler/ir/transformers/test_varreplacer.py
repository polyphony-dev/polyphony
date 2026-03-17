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


# ============================================================
# Additional VarReplacer tests for improved coverage
# ============================================================

from polyphony.compiler.ir.block import Block


def _make_scope_and_block():
    """Create a minimal scope with a block for testing VarReplacer."""
    setup_test()
    scope = Scope.create(None, 'S', {'function'}, 0)
    scope.add_sym('x', tags=set(), typ=Type.int(8))
    scope.add_sym('y', tags=set(), typ=Type.int(8))
    scope.add_sym('z', tags=set(), typ=Type.int(8))
    scope.add_sym('f', tags=set(), typ=Type.int(8))
    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)
    Block.set_order(blk, 0)
    return scope, blk


def test_visit_unop():
    """VarReplacer should replace inside UnOp."""
    scope, blk = _make_scope_and_block()
    unop = new.UnOp(op='Not', exp=Temp(name='x'))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(unop)
    assert isinstance(result, new.UnOp)
    assert isinstance(result.exp, new.Const)
    assert result.exp.value == 5


def test_visit_condop():
    """VarReplacer should replace inside CondOp."""
    scope, blk = _make_scope_and_block()
    condop = new.CondOp(cond=Temp(name='x'), left=Const(value=1), right=Const(value=2))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(condop)
    assert isinstance(result, new.CondOp)
    assert isinstance(result.cond, new.Const)
    assert result.cond.value == 5


def test_visit_call():
    """VarReplacer should replace inside Call arguments."""
    scope, blk = _make_scope_and_block()
    call = new.Call(func=Temp(name='f'), args=[('', Temp(name='x'))], kwargs={})

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(call)
    assert isinstance(result, new.Call)
    assert result.args[0][1].value == 5


def test_visit_syscall():
    """VarReplacer should replace inside SysCall arguments."""
    scope, blk = _make_scope_and_block()
    scope.add_sym('$fn', tags=set(), typ=Type.int(8))
    syscall = new.SysCall(func=Temp(name='$fn'), args=[('', Temp(name='x'))], kwargs={})

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(syscall)
    assert isinstance(result, new.SysCall)
    assert result.args[0][1].value == 5


def test_visit_new():
    """VarReplacer should replace inside New arguments."""
    scope, blk = _make_scope_and_block()
    scope.add_sym('C', tags=set(), typ=Type.int(8))
    new_ir = new.New(func=Temp(name='C'), args=[('', Temp(name='x'))], kwargs={})

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(new_ir)
    assert isinstance(result, new.New)
    assert result.args[0][1].value == 5


def test_visit_mref():
    """VarReplacer should replace inside MRef."""
    scope, blk = _make_scope_and_block()
    mref = new.MRef(mem=Temp(name='x'), offset=Const(value=0))

    replacer = VarReplacer(scope, Temp(name='x'), Temp(name='y'), None)
    result = replacer.visit(mref)
    assert isinstance(result, new.MRef)
    assert result.mem.name == 'y'


def test_visit_mstore():
    """VarReplacer should replace inside MStore."""
    scope, blk = _make_scope_and_block()
    mstore = new.MStore(mem=Temp(name='y'), offset=Temp(name='x'), exp=Const(value=1))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(mstore)
    assert isinstance(result, new.MStore)
    assert isinstance(result.offset, new.Const)
    assert result.offset.value == 5


def test_visit_array():
    """VarReplacer should replace inside Array items."""
    scope, blk = _make_scope_and_block()
    arr = new.Array(items=[Temp(name='x'), Const(value=2)], repeat=Const(value=1))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(arr)
    assert isinstance(result, new.Array)
    assert isinstance(result.items[0], new.Const)
    assert result.items[0].value == 5


def test_visit_move_stm():
    """VarReplacer should replace src in Move statement."""
    scope, blk = _make_scope_and_block()
    mv = new.Move(dst=Temp(name='y', ctx=new.Ctx.STORE), src=Temp(name='x'), block=blk)
    blk.stms = [mv]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(mv)
    assert isinstance(mv.src, new.Const)
    assert mv.src.value == 5
    assert mv in replacer.replaces


def test_visit_expr_stm():
    """VarReplacer should replace in Expr statement."""
    scope, blk = _make_scope_and_block()
    expr_stm = new.Expr(exp=Temp(name='x'), block=blk)
    blk.stms = [expr_stm]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(expr_stm)
    assert isinstance(expr_stm.exp, new.Const)
    assert expr_stm in replacer.replaces


def test_visit_cexpr_stm():
    """VarReplacer should replace in CExpr (cond + exp)."""
    scope, blk = _make_scope_and_block()
    # Put x in exp so it gets tracked in replaces (visit_CExpr resets replaced before visit_Expr)
    cexpr = new.CExpr(cond=Const(value=1), exp=Temp(name='x'), block=blk)
    blk.stms = [cexpr]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cexpr)
    assert isinstance(cexpr.exp, new.Const)
    assert cexpr.exp.value == 5
    assert cexpr in replacer.replaces


def test_visit_cexpr_cond_replacement():
    """VarReplacer should replace cond in CExpr."""
    scope, blk = _make_scope_and_block()
    cexpr = new.CExpr(cond=Temp(name='x'), exp=Const(value=1), block=blk)
    blk.stms = [cexpr]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cexpr)
    assert isinstance(cexpr.cond, new.Const)
    assert cexpr.cond.value == 5


def test_visit_cmove_stm():
    """VarReplacer should replace in CMove src."""
    scope, blk = _make_scope_and_block()
    # Put x in src so it gets tracked in replaces
    cmove = new.CMove(cond=Const(value=1), dst=Temp(name='y', ctx=new.Ctx.STORE),
                       src=Temp(name='x'), block=blk)
    blk.stms = [cmove]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cmove)
    assert isinstance(cmove.src, new.Const)
    assert cmove.src.value == 5
    assert cmove in replacer.replaces


def test_visit_cmove_cond_replacement():
    """VarReplacer should replace cond in CMove."""
    scope, blk = _make_scope_and_block()
    cmove = new.CMove(cond=Temp(name='x'), dst=Temp(name='y', ctx=new.Ctx.STORE),
                       src=Const(value=1), block=blk)
    blk.stms = [cmove]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cmove)
    assert isinstance(cmove.cond, new.Const)
    assert cmove.cond.value == 5


def test_visit_cjump_stm():
    """VarReplacer should replace exp in CJump."""
    scope, blk = _make_scope_and_block()
    blk2 = Block(scope, nametag='blk2')
    blk3 = Block(scope, nametag='blk3')
    cjump = new.CJump(exp=Temp(name='x'), true=blk2, false=blk3, block=blk)
    blk.stms = [cjump]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cjump)
    assert isinstance(cjump.exp, new.Const)
    assert cjump.exp.value == 5
    assert cjump in replacer.replaces


def test_visit_mcjump_stm():
    """VarReplacer should replace conds in MCJump."""
    scope, blk = _make_scope_and_block()
    blk2 = Block(scope, nametag='blk2')
    blk3 = Block(scope, nametag='blk3')
    mcjump = new.MCJump(conds=[Temp(name='x'), Const(value=1)],
                         targets=[blk2, blk3], block=blk)
    blk.stms = [mcjump]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(mcjump)
    assert isinstance(mcjump.conds[0], new.Const)
    assert mcjump.conds[0].value == 5
    assert mcjump in replacer.replaces


def test_visit_phi_stm():
    """VarReplacer should replace in Phi args and ps."""
    scope, blk = _make_scope_and_block()
    phi = new.Phi(var=Temp(name='y', ctx=new.Ctx.STORE),
                   args=[Temp(name='x'), Const(value=2)],
                   ps=[Const(value=1), Temp(name='x')],
                   block=blk)
    blk.stms = [phi]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(phi)
    assert isinstance(phi.args[0], new.Const)
    assert phi.args[0].value == 5
    assert isinstance(phi.ps[1], new.Const)
    assert phi.ps[1].value == 5
    assert phi in replacer.replaces


def test_visit_uphi_stm():
    """VarReplacer should replace in UPhi."""
    scope, blk = _make_scope_and_block()
    uphi = new.UPhi(var=Temp(name='y', ctx=new.Ctx.STORE),
                     args=[Temp(name='x')],
                     ps=[Const(value=1)],
                     block=blk)
    blk.stms = [uphi]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(uphi)
    assert isinstance(uphi.args[0], new.Const)
    assert uphi in replacer.replaces


def test_visit_lphi_stm():
    """VarReplacer should replace in LPhi."""
    scope, blk = _make_scope_and_block()
    lphi = new.LPhi(var=Temp(name='y', ctx=new.Ctx.STORE),
                     args=[Temp(name='x')],
                     ps=[Const(value=1)],
                     block=blk)
    blk.stms = [lphi]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(lphi)
    assert isinstance(lphi.args[0], new.Const)
    assert lphi in replacer.replaces


def test_visit_jump_and_ret():
    """VarReplacer.visit_Jump and visit_Ret should not crash."""
    scope, blk = _make_scope_and_block()
    blk2 = Block(scope, nametag='blk2')

    jump = new.Jump(blk2, block=blk)
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(jump)
    assert result is None

    ret = new.Ret(exp=Temp(name='z'), block=blk)
    result = replacer.visit(ret)
    assert result is None


def test_visit_const():
    """VarReplacer.visit_Const should return the const unchanged."""
    scope, blk = _make_scope_and_block()
    c = Const(value=42)
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(c)
    assert result is c


def test_replace_uses_classmethod():
    """VarReplacer.replace_uses should replace all uses in a scope."""
    scope, blk = _make_scope_and_block()
    mv = new.Move(dst=Temp(name='y', ctx=new.Ctx.STORE), src=Temp(name='x'), block=blk)
    blk.stms = [mv]

    replaces = VarReplacer.replace_uses(scope, Temp(name='x'), Const(value=99))
    assert len(replaces) >= 1
    assert isinstance(mv.src, new.Const)
    assert mv.src.value == 99


def test_move_with_enable_dst():
    """VarReplacer with enable_dst should also replace in Move.dst."""
    scope, blk = _make_scope_and_block()
    mv = new.Move(dst=Temp(name='x', ctx=new.Ctx.STORE), src=Const(value=1), block=blk)
    blk.stms = [mv]

    replacer = VarReplacer(scope, Temp(name='x'), Temp(name='z'), None, enable_dst=True)
    replacer.visit(mv)
    assert mv.dst.name == 'z'


def test_phi_with_enable_dst():
    """VarReplacer with enable_dst should replace Phi.var."""
    scope, blk = _make_scope_and_block()
    phi = new.Phi(var=Temp(name='x', ctx=new.Ctx.STORE),
                   args=[Const(value=1)],
                   ps=[Const(value=1)],
                   block=blk)
    blk.stms = [phi]

    replacer = VarReplacer(scope, Temp(name='x'), Temp(name='z'), None, enable_dst=True)
    replacer.visit(phi)
    assert phi.var.name == 'z'


def test_no_change_returns_same_object():
    """When no replacement happens, visit should return the same object."""
    scope, blk = _make_scope_and_block()
    unop = new.UnOp(op='Not', exp=Temp(name='y'))
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(unop)
    assert result is unop

    binop = new.BinOp(op='Add', left=Temp(name='y'), right=Const(value=1))
    result = replacer.visit(binop)
    assert result is binop

    relop = new.RelOp(op='Eq', left=Temp(name='y'), right=Const(value=1))
    result = replacer.visit(relop)
    assert result is relop

    condop = new.CondOp(cond=Temp(name='y'), left=Const(value=1), right=Const(value=2))
    result = replacer.visit(condop)
    assert result is condop

    call = new.Call(func=Temp(name='f'), args=[('', Temp(name='y'))], kwargs={})
    result = replacer.visit(call)
    assert result is call

    mref = new.MRef(mem=Temp(name='y'), offset=Const(value=0))
    result = replacer.visit(mref)
    assert result is mref

    mstore = new.MStore(mem=Temp(name='y'), offset=Const(value=0), exp=Const(value=1))
    result = replacer.visit(mstore)
    assert result is mstore

    arr = new.Array(items=[Temp(name='y')], repeat=Const(value=1))
    result = replacer.visit(arr)
    assert result is arr
