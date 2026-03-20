"""Tests for VarReplacer, especially ExprType.expr handling."""
from polyphony.compiler.ir.ir import (
    Temp, Const, Ctx, Expr, Move, Call, New, BinOp, RelOp, UnOp,
    MRef, MStore, Array, SysCall, Phi, UPhi, LPhi, Jump, CJump, MCJump, Ret, Attr,
    CondOp, CExpr, CMove,
)
from polyphony.compiler.ir.transformers.varreplacer import VarReplacer
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.types.exprtype import ExprType
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_visit_with_context_new_ir_expr():
    """VarReplacer.visit_with_context returns a new Expr with the replacement applied.
    Orphan Exprs (no block) are not mutated in-place; a new stm is returned."""
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(8))
    scope.add_sym('y', tags=set(), typ=Type.int(8))

    # Create new IR Expr containing Temp('x') (orphan: no block)
    new_expr = Expr(exp=Temp(name='x'))

    # Create VarReplacer to replace x -> Const(5)
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit_with_context(scope, new_expr)

    # The returned Expr should have x replaced with Const(5)
    assert result is not new_expr
    assert isinstance(result.exp, Const)
    assert result.exp.value == 5
    # Original is unchanged (immutable)
    assert isinstance(new_expr.exp, Temp)


def test_visit_with_context_new_ir():
    """VarReplacer.visit_with_context returns a new stm with the replacement applied."""
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(8))

    new_expr = Expr(exp=Temp(name='x'))
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit_with_context(scope, new_expr)

    assert result is not new_expr
    assert isinstance(result.exp, Const)
    assert result.exp.value == 5


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
    unop = UnOp(op='Not', exp=Temp(name='x'))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(unop)
    assert isinstance(result, UnOp)
    assert isinstance(result.exp, Const)
    assert result.exp.value == 5


def test_visit_condop():
    """VarReplacer should replace inside CondOp."""
    scope, blk = _make_scope_and_block()
    condop = CondOp(cond=Temp(name='x'), left=Const(value=1), right=Const(value=2))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(condop)
    assert isinstance(result, CondOp)
    assert isinstance(result.cond, Const)
    assert result.cond.value == 5


def test_visit_call():
    """VarReplacer should replace inside Call arguments."""
    scope, blk = _make_scope_and_block()
    call = Call(func=Temp(name='f'), args=[('', Temp(name='x'))], kwargs={})

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(call)
    assert isinstance(result, Call)
    assert result.args[0][1].value == 5


def test_visit_syscall():
    """VarReplacer should replace inside SysCall arguments."""
    scope, blk = _make_scope_and_block()
    scope.add_sym('$fn', tags=set(), typ=Type.int(8))
    syscall = SysCall(func=Temp(name='$fn'), args=[('', Temp(name='x'))], kwargs={})

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(syscall)
    assert isinstance(result, SysCall)
    assert result.args[0][1].value == 5


def test_visit_new():
    """VarReplacer should replace inside New arguments."""
    scope, blk = _make_scope_and_block()
    scope.add_sym('C', tags=set(), typ=Type.int(8))
    new_ir = New(func=Temp(name='C'), args=[('', Temp(name='x'))], kwargs={})

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(new_ir)
    assert isinstance(result, New)
    assert result.args[0][1].value == 5


def test_visit_mref():
    """VarReplacer should replace inside MRef."""
    scope, blk = _make_scope_and_block()
    mref = MRef(mem=Temp(name='x'), offset=Const(value=0))

    replacer = VarReplacer(scope, Temp(name='x'), Temp(name='y'), None)
    result = replacer.visit(mref)
    assert isinstance(result, MRef)
    assert result.mem.name == 'y'


def test_visit_mstore():
    """VarReplacer should replace inside MStore."""
    scope, blk = _make_scope_and_block()
    mstore = MStore(mem=Temp(name='y'), offset=Temp(name='x'), exp=Const(value=1))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(mstore)
    assert isinstance(result, MStore)
    assert isinstance(result.offset, Const)
    assert result.offset.value == 5


def test_visit_array():
    """VarReplacer should replace inside Array items."""
    scope, blk = _make_scope_and_block()
    arr = Array(items=[Temp(name='x'), Const(value=2)], repeat=Const(value=1))

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(arr)
    assert isinstance(result, Array)
    assert isinstance(result.items[0], Const)
    assert result.items[0].value == 5


def test_visit_move_stm():
    """VarReplacer should replace src in Move statement."""
    scope, blk = _make_scope_and_block()
    mv = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Temp(name='x'), block=blk.bid)
    blk.stms = [mv]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(mv)
    # model_copy creates a new stm in the block
    new_mv = blk.stms[0]
    assert isinstance(new_mv.src, Const)
    assert new_mv.src.value == 5
    assert new_mv in replacer.replaces


def test_visit_expr_stm():
    """VarReplacer should replace in Expr statement."""
    scope, blk = _make_scope_and_block()
    expr_stm = Expr(exp=Temp(name='x'), block=blk.bid)
    blk.stms = [expr_stm]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(expr_stm)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.exp, Const)
    assert new_stm in replacer.replaces


def test_visit_cexpr_stm():
    """VarReplacer should replace in CExpr (cond + exp)."""
    scope, blk = _make_scope_and_block()
    # Put x in exp so it gets tracked in replaces
    cexpr = CExpr(cond=Const(value=1), exp=Temp(name='x'), block=blk.bid)
    blk.stms = [cexpr]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cexpr)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.exp, Const)
    assert new_stm.exp.value == 5
    assert new_stm in replacer.replaces


def test_visit_cexpr_cond_replacement():
    """VarReplacer should replace cond in CExpr."""
    scope, blk = _make_scope_and_block()
    cexpr = CExpr(cond=Temp(name='x'), exp=Const(value=1), block=blk.bid)
    blk.stms = [cexpr]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cexpr)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.cond, Const)
    assert new_stm.cond.value == 5


def test_visit_cmove_stm():
    """VarReplacer should replace in CMove src."""
    scope, blk = _make_scope_and_block()
    # Put x in src so it gets tracked in replaces
    cmove = CMove(cond=Const(value=1), dst=Temp(name='y', ctx=Ctx.STORE),
                       src=Temp(name='x'), block=blk.bid)
    blk.stms = [cmove]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cmove)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.src, Const)
    assert new_stm.src.value == 5
    assert new_stm in replacer.replaces


def test_visit_cmove_cond_replacement():
    """VarReplacer should replace cond in CMove."""
    scope, blk = _make_scope_and_block()
    cmove = CMove(cond=Temp(name='x'), dst=Temp(name='y', ctx=Ctx.STORE),
                       src=Const(value=1), block=blk.bid)
    blk.stms = [cmove]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cmove)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.cond, Const)
    assert new_stm.cond.value == 5


def test_visit_cjump_stm():
    """VarReplacer should replace exp in CJump."""
    scope, blk = _make_scope_and_block()
    blk2 = Block(scope, nametag='blk2')
    blk3 = Block(scope, nametag='blk3')
    cjump = CJump(exp=Temp(name='x'), true=blk2.bid, false=blk3.bid, block=blk.bid)
    blk.stms = [cjump]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(cjump)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.exp, Const)
    assert new_stm.exp.value == 5
    assert new_stm in replacer.replaces


def test_visit_mcjump_stm():
    """VarReplacer should replace conds in MCJump."""
    scope, blk = _make_scope_and_block()
    blk2 = Block(scope, nametag='blk2')
    blk3 = Block(scope, nametag='blk3')
    mcjump = MCJump(conds=[Temp(name='x'), Const(value=1)],
                         targets=[blk2.bid, blk3.bid], block=blk.bid)
    blk.stms = [mcjump]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(mcjump)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.conds[0], Const)
    assert new_stm.conds[0].value == 5
    assert new_stm in replacer.replaces


def test_visit_phi_stm():
    """VarReplacer should replace in Phi args and ps."""
    scope, blk = _make_scope_and_block()
    phi = Phi(var=Temp(name='y', ctx=Ctx.STORE),
                   args=[Temp(name='x'), Const(value=2)],
                   ps=[Const(value=1), Temp(name='x')], block=blk.bid)
    blk.stms = [phi]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(phi)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.args[0], Const)
    assert new_stm.args[0].value == 5
    assert isinstance(new_stm.ps[1], Const)
    assert new_stm.ps[1].value == 5
    assert new_stm in replacer.replaces


def test_visit_uphi_stm():
    """VarReplacer should replace in UPhi."""
    scope, blk = _make_scope_and_block()
    uphi = UPhi(var=Temp(name='y', ctx=Ctx.STORE),
                     args=[Temp(name='x')],
                     ps=[Const(value=1)], block=blk.bid)
    blk.stms = [uphi]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(uphi)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.args[0], Const)
    assert new_stm in replacer.replaces


def test_visit_lphi_stm():
    """VarReplacer should replace in LPhi."""
    scope, blk = _make_scope_and_block()
    lphi = LPhi(var=Temp(name='y', ctx=Ctx.STORE),
                     args=[Temp(name='x')],
                     ps=[Const(value=1)], block=blk.bid)
    blk.stms = [lphi]

    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    replacer.visit(lphi)
    new_stm = blk.stms[0]
    assert isinstance(new_stm.args[0], Const)
    assert new_stm in replacer.replaces


def test_visit_jump_and_ret():
    """VarReplacer.visit_Jump and visit_Ret should not crash."""
    scope, blk = _make_scope_and_block()
    blk2 = Block(scope, nametag='blk2')

    jump = Jump(blk2.bid, block=blk.bid)
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(jump)
    assert result is None

    ret = Ret(exp=Temp(name='z'), block=blk.bid)
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
    mv = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Temp(name='x'), block=blk.bid)
    blk.stms = [mv]

    replaces = VarReplacer.replace_uses(scope, Temp(name='x'), Const(value=99))
    assert len(replaces) >= 1
    new_mv = blk.stms[0]
    assert isinstance(new_mv.src, Const)
    assert new_mv.src.value == 99


def test_move_with_enable_dst():
    """VarReplacer with enable_dst should also replace in Move.dst."""
    scope, blk = _make_scope_and_block()
    mv = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1), block=blk.bid)
    blk.stms = [mv]

    replacer = VarReplacer(scope, Temp(name='x'), Temp(name='z'), None, enable_dst=True)
    replacer.visit(mv)
    new_mv = blk.stms[0]
    assert new_mv.dst.name == 'z'


def test_phi_with_enable_dst():
    """VarReplacer with enable_dst should replace Phi.var."""
    scope, blk = _make_scope_and_block()
    phi = Phi(var=Temp(name='x', ctx=Ctx.STORE),
                   args=[Const(value=1)],
                   ps=[Const(value=1)], block=blk.bid)
    blk.stms = [phi]

    replacer = VarReplacer(scope, Temp(name='x'), Temp(name='z'), None, enable_dst=True)
    replacer.visit(phi)
    new_phi = blk.stms[0]
    assert new_phi.var.name == 'z'


def test_no_change_returns_same_object():
    """When no replacement happens, visit should return the same object."""
    scope, blk = _make_scope_and_block()
    unop = UnOp(op='Not', exp=Temp(name='y'))
    replacer = VarReplacer(scope, Temp(name='x'), Const(value=5), None)
    result = replacer.visit(unop)
    assert result is unop

    binop = BinOp(op='Add', left=Temp(name='y'), right=Const(value=1))
    result = replacer.visit(binop)
    assert result is binop

    relop = RelOp(op='Eq', left=Temp(name='y'), right=Const(value=1))
    result = replacer.visit(relop)
    assert result is relop

    condop = CondOp(cond=Temp(name='y'), left=Const(value=1), right=Const(value=2))
    result = replacer.visit(condop)
    assert result is condop

    call = Call(func=Temp(name='f'), args=[('', Temp(name='y'))], kwargs={})
    result = replacer.visit(call)
    assert result is call

    mref = MRef(mem=Temp(name='y'), offset=Const(value=0))
    result = replacer.visit(mref)
    assert result is mref

    mstore = MStore(mem=Temp(name='y'), offset=Const(value=0), exp=Const(value=1))
    result = replacer.visit(mstore)
    assert result is mstore

    arr = Array(items=[Temp(name='y')], repeat=Const(value=1))
    result = replacer.visit(arr)
    assert result is arr
