"""Tests for PHIInlining and LPHIRemover."""
from polyphony.compiler.ir.ir import (
    Const, Temp, Move, CJump, BinOp, RelOp, UnOp,
    LPhi, Phi, UPhi, Jump, Ret, Expr, Ctx, Loc, MStm,
)
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import (
    LoopDetector, LoopInfoSetter, LoopDependencyDetector,
)
from polyphony.compiler.ir.transformers.phiopt import PHIInlining, LPHIRemover
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ===========================================================
# Helper: build a scope with a simple loop containing LPhi
# ===========================================================

def _build_simple_loop_scope():
    """Build a scope with a single loop: entry -> loop_head -> loop_body -> loop_head, loop_head -> loop_exit."""
    setup_test()
    scope = Scope.create(None, 'LPhiTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i_init', tags=set(), typ=Type.int())
    scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    scope.add_sym('cond', tags={'condition'}, typ=Type.bool())

    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    blk_entry.append_stm(Move(Temp('i_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Jump(loop_head))

    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', [Temp('i_init'), Temp('i_upd')])
    object.__setattr__(i_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(i_lphi)
    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(10))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body, loop_exit))

    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    loop_body.append_stm(Jump(loop_head, typ='L'))

    loop_exit.append_stm(Move(Temp('@return', Ctx.STORE), Temp('i')))
    loop_exit.append_stm(Ret(Temp('@return')))

    blk_entry.succs = [loop_head]
    loop_head.preds = [blk_entry, loop_body]
    loop_head.preds_loop = [loop_body]
    loop_head.succs = [loop_body, loop_exit]
    loop_body.preds = [loop_head]
    loop_body.succs = [loop_head]
    loop_body.succs_loop = [loop_head]
    loop_exit.preds = [loop_head]

    Block.set_order(blk_entry, 0)
    LoopDetector().process(scope)
    LoopInfoSetter().process(scope)
    LoopDependencyDetector().process(scope)
    return scope


def _build_multi_lphi_loop_scope():
    """Build a scope with two LPhi variables in the same loop head."""
    setup_test()
    scope = Scope.create(None, 'MultiLPhi', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i_init', tags=set(), typ=Type.int())
    scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    scope.add_sym('acc_init', tags=set(), typ=Type.int())
    scope.add_sym('acc', tags=set(), typ=Type.int())
    scope.add_sym('acc_upd', tags=set(), typ=Type.int())
    scope.add_sym('cond', tags={'condition'}, typ=Type.bool())

    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    blk_entry.append_stm(Move(Temp('i_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Move(Temp('acc_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Jump(loop_head))

    # LPhi for i (induction variable)
    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', [Temp('i_init'), Temp('i_upd')])
    object.__setattr__(i_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(i_lphi)

    # LPhi for acc (non-induction)
    acc_lphi = LPhi(Temp('acc', Ctx.STORE))
    object.__setattr__(acc_lphi, 'args', [Temp('acc_init'), Temp('acc_upd')])
    object.__setattr__(acc_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(acc_lphi)

    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(10))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body, loop_exit))

    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    loop_body.append_stm(Move(Temp('acc_upd', Ctx.STORE), BinOp('Add', Temp('acc'), Temp('i'))))
    loop_body.append_stm(Jump(loop_head, typ='L'))

    loop_exit.append_stm(Move(Temp('@return', Ctx.STORE), Temp('acc')))
    loop_exit.append_stm(Ret(Temp('@return')))

    blk_entry.succs = [loop_head]
    loop_head.preds = [blk_entry, loop_body]
    loop_head.preds_loop = [loop_body]
    loop_head.succs = [loop_body, loop_exit]
    loop_body.preds = [loop_head]
    loop_body.succs = [loop_head]
    loop_body.succs_loop = [loop_head]
    loop_exit.preds = [loop_head]

    Block.set_order(blk_entry, 0)
    LoopDetector().process(scope)
    LoopInfoSetter().process(scope)
    LoopDependencyDetector().process(scope)
    return scope


def _build_phi_scope_no_phi():
    """Build a scope with no PHI/UPhi statements (only Move)."""
    setup_test()
    scope = Scope.create(None, 'NoPhi', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('x', tags=set(), typ=Type.int())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    blk.append_stm(Move(Temp('x', Ctx.STORE), Const(42)))
    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('x')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)
    return scope


def _build_phi_scope_with_induction_phi():
    """Build a scope with a Phi whose var is an induction variable (should be skipped)."""
    setup_test()
    scope = Scope.create(None, 'InductionPhi', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i', tags={'induction'}, typ=Type.int())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    # A Phi for an induction variable -- PHIInlining should skip it
    phi_i = Phi(Temp('i', Ctx.STORE))
    object.__setattr__(phi_i, 'args', [Const(0), Const(1)])
    object.__setattr__(phi_i, 'ps', [Const(1), Const(1)])
    blk.append_stm(phi_i)
    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('i')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)
    return scope


def _build_phi_scope_with_non_induction_phi():
    """Build a scope with Phi/UPhi for non-induction vars."""
    setup_test()
    scope = Scope.create(None, 'NonInductionPhi', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('a', tags=set(), typ=Type.int())
    scope.add_sym('b', tags=set(), typ=Type.int())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    # Phi for non-induction 'a'
    phi_a = Phi(Temp('a', Ctx.STORE))
    object.__setattr__(phi_a, 'args', [Const(10), Const(20)])
    object.__setattr__(phi_a, 'ps', [Const(1), Const(1)])
    blk.append_stm(phi_a)

    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('a')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)
    return scope


def _build_phi_scope_with_inlining():
    """Build a scope where one Phi arg references another Phi's var (triggers inlining)."""
    setup_test()
    scope = Scope.create(None, 'PhiInline', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('a', tags=set(), typ=Type.int())
    scope.add_sym('b', tags=set(), typ=Type.int())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    p1 = Temp('p1')
    p2 = Temp('p2')
    p3 = Temp('p3')
    scope.add_sym('p1', tags={'condition'}, typ=Type.bool())
    scope.add_sym('p2', tags={'condition'}, typ=Type.bool())
    scope.add_sym('p3', tags={'condition'}, typ=Type.bool())

    # Phi for 'a': a = phi(10, 20) with predicates p1, p2
    phi_a = Phi(Temp('a', Ctx.STORE))
    object.__setattr__(phi_a, 'args', [Const(10), Const(20)])
    object.__setattr__(phi_a, 'ps', [p1, p2])
    blk.append_stm(phi_a)

    # Phi for 'b': b = phi(a, 30) with predicates p3, Const(1)
    # Since arg 'a' is a Temp referencing Phi 'a', this should be inlined
    phi_b = UPhi(Temp('b', Ctx.STORE))
    object.__setattr__(phi_b, 'args', [Temp('a'), Const(30)])
    object.__setattr__(phi_b, 'ps', [p3, Const(1)])
    blk.append_stm(phi_b)

    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('b')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)
    return scope


def _build_phi_scope_const_args():
    """Build a scope with Phi that has only Const args (no inlining triggered)."""
    setup_test()
    scope = Scope.create(None, 'PhiConstArgs', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('x', tags=set(), typ=Type.int())
    scope.add_sym('c1', tags={'condition'}, typ=Type.bool())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    c1 = Temp('c1')

    phi_x = Phi(Temp('x', Ctx.STORE))
    object.__setattr__(phi_x, 'args', [Const(1), Const(2)])
    object.__setattr__(phi_x, 'ps', [c1, Const(1)])
    blk.append_stm(phi_x)

    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('x')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)
    return scope


def _build_loop_scope_no_lphi():
    """Build a loop scope with no LPhi in loop head.

    Uses LPhi-free structure with separate init/update symbols
    to keep LoopInfoSetter happy (single def per induction var).
    """
    setup_test()
    scope = Scope.create(None, 'NoLPhi', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i_init', tags=set(), typ=Type.int())
    scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    scope.add_sym('cond', tags={'condition'}, typ=Type.bool())

    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    blk_entry.append_stm(Move(Temp('i_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Jump(loop_head))

    # No LPhi here -- just use 'i' via a Phi (not LPhi) or direct use
    # Use a regular Phi to satisfy structure but not an LPhi
    phi_i = Phi(Temp('i', Ctx.STORE))
    object.__setattr__(phi_i, 'args', [Temp('i_init'), Temp('i_upd')])
    object.__setattr__(phi_i, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(phi_i)
    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(10))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body, loop_exit))

    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    loop_body.append_stm(Jump(loop_head, typ='L'))

    loop_exit.append_stm(Move(Temp('@return', Ctx.STORE), Temp('i')))
    loop_exit.append_stm(Ret(Temp('@return')))

    blk_entry.succs = [loop_head]
    loop_head.preds = [blk_entry, loop_body]
    loop_head.preds_loop = [loop_body]
    loop_head.succs = [loop_body, loop_exit]
    loop_body.preds = [loop_head]
    loop_body.succs = [loop_head]
    loop_body.succs_loop = [loop_head]
    loop_exit.preds = [loop_head]

    Block.set_order(blk_entry, 0)
    LoopDetector().process(scope)
    LoopInfoSetter().process(scope)
    LoopDependencyDetector().process(scope)
    return scope


# ===========================================================
# PHIInlining tests
# ===========================================================

def test_phi_inlining_class_exists():
    """PHIInlining class can be imported and instantiated."""
    inliner = PHIInlining()
    assert inliner is not None


def test_phi_inlining_no_phi_stms():
    """PHIInlining is a no-op when there are no Phi/UPhi statements."""
    scope = _build_phi_scope_no_phi()
    blk = scope.entry_block
    stms_before = list(blk.stms)

    PHIInlining().process(scope)

    # Statements should be unchanged
    assert len(blk.stms) == len(stms_before)
    for s_before, s_after in zip(stms_before, blk.stms):
        assert s_before is s_after


def test_phi_inlining_skips_induction_var():
    """PHIInlining skips Phi whose var is an induction variable."""
    scope = _build_phi_scope_with_induction_phi()
    blk = scope.entry_block
    phi = blk.stms[0]
    assert isinstance(phi, Phi)

    # Capture args before
    args_before = list(phi.args)
    ps_before = list(phi.ps)

    PHIInlining().process(scope)

    # Induction phi should not be collected, hence no inlining
    # (there are no other phis to inline into, so args should remain unchanged)
    assert phi.args == args_before
    assert phi.ps == ps_before


def test_phi_inlining_collects_non_induction_phi():
    """PHIInlining collects Phi with non-induction var for potential inlining."""
    scope = _build_phi_scope_with_non_induction_phi()
    blk = scope.entry_block
    phi_a = blk.stms[0]
    assert isinstance(phi_a, Phi)

    # Only one phi with const args, no inlining will happen, but it should
    # be processed without error (const args don't reference other phis)
    args_before = list(phi_a.args)

    PHIInlining().process(scope)

    # Args should remain the same (no other phi to inline from)
    assert phi_a.args == args_before


def test_phi_inlining_inlines_phi_arg():
    """PHIInlining inlines a Phi when one arg references another Phi's var."""
    scope = _build_phi_scope_with_inlining()
    blk = scope.entry_block

    phi_a = blk.stms[0]
    phi_b = blk.stms[1]
    assert isinstance(phi_a, Phi)
    assert isinstance(phi_b, UPhi)

    # Before: phi_b has args=[Temp('a'), Const(30)] and ps=[p3, Const(1)]
    assert len(phi_b.args) == 2
    assert isinstance(phi_b.args[0], Temp) and phi_b.args[0].name == 'a'
    assert isinstance(phi_b.args[1], Const) and phi_b.args[1].value == 30

    PHIInlining().process(scope)

    # After inlining: phi_b.args[0] (Temp('a')) is replaced by phi_a's args
    # phi_a has args=[Const(10), Const(20)], so phi_b should now have
    # args=[Const(10), Const(20), Const(30)]
    assert len(phi_b.args) == 3
    assert isinstance(phi_b.args[0], Const) and phi_b.args[0].value == 10
    assert isinstance(phi_b.args[1], Const) and phi_b.args[1].value == 20
    assert isinstance(phi_b.args[2], Const) and phi_b.args[2].value == 30

    # The ps should also be expanded: original p3 is combined with phi_a's ps
    assert len(phi_b.ps) == 3


def test_phi_inlining_const_args_no_change():
    """PHIInlining does not inline Phi args that are Const (not IrVariable)."""
    scope = _build_phi_scope_const_args()
    blk = scope.entry_block
    phi_x = blk.stms[0]
    assert isinstance(phi_x, Phi)

    args_before = list(phi_x.args)
    ps_before = list(phi_x.ps)

    PHIInlining().process(scope)

    # Const args do not trigger inlining
    assert len(phi_x.args) == len(args_before)
    for a, b in zip(phi_x.args, args_before):
        assert type(a) is type(b)


def test_phi_inlining_self_reference_not_inlined():
    """PHIInlining does not inline a Phi into itself (phi != phis[arg_sym] check)."""
    setup_test()
    scope = Scope.create(None, 'SelfRef', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('a', tags=set(), typ=Type.int())
    scope.add_sym('c', tags={'condition'}, typ=Type.bool())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    # Phi for 'a' that references itself
    phi_a = Phi(Temp('a', Ctx.STORE))
    object.__setattr__(phi_a, 'args', [Temp('a'), Const(5)])
    object.__setattr__(phi_a, 'ps', [Temp('c'), Const(1)])
    blk.append_stm(phi_a)
    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('a')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)

    args_before = list(phi_a.args)
    PHIInlining().process(scope)

    # Self-referencing phi should not be inlined (phi == phis[arg_sym])
    assert len(phi_a.args) == len(args_before)


def test_phi_inlining_mixed_induction_and_non_induction():
    """PHIInlining only collects non-induction phis; induction phis are ignored."""
    setup_test()
    scope = Scope.create(None, 'Mixed', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('x', tags=set(), typ=Type.int())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    # Phi for induction 'i'
    phi_i = Phi(Temp('i', Ctx.STORE))
    object.__setattr__(phi_i, 'args', [Const(0), Const(1)])
    object.__setattr__(phi_i, 'ps', [Const(1), Const(1)])
    blk.append_stm(phi_i)

    # Phi for non-induction 'x' referencing 'i'
    phi_x = Phi(Temp('x', Ctx.STORE))
    object.__setattr__(phi_x, 'args', [Temp('i'), Const(99)])
    object.__setattr__(phi_x, 'ps', [Const(1), Const(1)])
    blk.append_stm(phi_x)

    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('x')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)

    PHIInlining().process(scope)

    # 'i' is induction so not in phis dict, so Temp('i') in phi_x should not be inlined
    assert len(phi_x.args) == 2
    assert isinstance(phi_x.args[0], Temp) and phi_x.args[0].name == 'i'


def test_phi_inlining_uphi_collected():
    """PHIInlining collects both Phi and UPhi for non-induction variables."""
    setup_test()
    scope = Scope.create(None, 'UPhiCollect', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('a', tags=set(), typ=Type.int())
    scope.add_sym('b', tags=set(), typ=Type.int())
    scope.add_sym('c1', tags={'condition'}, typ=Type.bool())
    scope.add_sym('c2', tags={'condition'}, typ=Type.bool())

    blk = Block(scope, nametag='blk1')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    # UPhi for 'a'
    uphi_a = UPhi(Temp('a', Ctx.STORE))
    object.__setattr__(uphi_a, 'args', [Const(1), Const(2)])
    object.__setattr__(uphi_a, 'ps', [Temp('c1'), Temp('c2')])
    blk.append_stm(uphi_a)

    # Phi for 'b' that references 'a'
    phi_b = Phi(Temp('b', Ctx.STORE))
    object.__setattr__(phi_b, 'args', [Temp('a'), Const(3)])
    object.__setattr__(phi_b, 'ps', [Const(1), Const(1)])
    blk.append_stm(phi_b)

    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('b')))
    blk.append_stm(Ret(Temp('@return')))

    Block.set_order(blk, 0)

    PHIInlining().process(scope)

    # phi_b's first arg (Temp('a')) should be inlined from uphi_a
    assert len(phi_b.args) == 3
    assert isinstance(phi_b.args[0], Const) and phi_b.args[0].value == 1
    assert isinstance(phi_b.args[1], Const) and phi_b.args[1].value == 2
    assert isinstance(phi_b.args[2], Const) and phi_b.args[2].value == 3


# ===========================================================
# LPHIRemover tests
# ===========================================================

def test_lphi_remover_class_exists():
    """LPHIRemover class can be imported and instantiated."""
    remover = LPHIRemover()
    assert remover is not None


def test_lphi_remover_no_lphi():
    """LPHIRemover is a no-op when loop head has no LPhi."""
    scope = _build_loop_scope_no_lphi()

    # Count stms before
    stm_counts = {}
    for blk in scope.traverse_blocks():
        stm_counts[blk.name] = len(blk.stms)

    LPHIRemover().process(scope)

    # No LPhi => no changes
    for blk in scope.traverse_blocks():
        assert len(blk.stms) == stm_counts[blk.name]


def test_lphi_remover_single_lphi():
    """LPHIRemover converts a single LPhi to Move statements."""
    scope = _build_simple_loop_scope()

    # Before: loop_head should have an LPhi
    loop_head = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'loop_head':
            loop_head = blk
            break
    assert loop_head is not None
    lphis_before = loop_head.collect_stms([LPhi])
    assert len(lphis_before) == 1

    LPHIRemover().process(scope)

    # After: LPhi should be removed from loop_head
    lphis_after = loop_head.collect_stms([LPhi])
    assert len(lphis_after) == 0

    # The entry block (pred at init index) should have a Move for the init arg
    entry_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'entry':
            entry_blk = blk
            break
    assert entry_blk is not None
    init_moves = [s for s in entry_blk.stms if isinstance(s, Move) and
                  isinstance(s.dst, Temp) and s.dst.name == 'i']
    assert len(init_moves) == 1, "Should have a Move for LPhi init arg in entry block"

    # The loop body (preds_loop[0]) should have an MStm with Move for the update arg
    loop_body = loop_head.preds_loop[0]
    mstms = [s for s in loop_body.stms if isinstance(s, MStm)]
    assert len(mstms) == 1, "Should have an MStm in loop body"
    assert len(mstms[0].stms) == 1
    assert isinstance(mstms[0].stms[0], Move)
    assert mstms[0].stms[0].dst.name == 'i'


def test_lphi_remover_multiple_lphis():
    """LPHIRemover handles multiple LPhis in the same loop head."""
    scope = _build_multi_lphi_loop_scope()

    loop_head = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'loop_head':
            loop_head = blk
            break
    assert loop_head is not None
    lphis_before = loop_head.collect_stms([LPhi])
    assert len(lphis_before) == 2

    LPHIRemover().process(scope)

    # After: all LPhis should be removed from loop_head
    lphis_after = loop_head.collect_stms([LPhi])
    assert len(lphis_after) == 0

    # Entry block should have Move stms for both init args
    entry_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'entry':
            entry_blk = blk
            break
    init_move_names = {s.dst.name for s in entry_blk.stms
                       if isinstance(s, Move) and isinstance(s.dst, Temp)
                       and s.dst.name in ('i', 'acc')}
    assert 'i' in init_move_names, "Entry should have Move for i init"
    assert 'acc' in init_move_names, "Entry should have Move for acc init"

    # Loop body should have MStm with 2 Move stms (one per LPhi)
    loop_body = loop_head.preds_loop[0]
    mstms = [s for s in loop_body.stms if isinstance(s, MStm)]
    assert len(mstms) == 1
    assert len(mstms[0].stms) == 2
    move_names = {m.dst.name for m in mstms[0].stms if isinstance(m, Move)}
    assert 'i' in move_names
    assert 'acc' in move_names


def test_lphi_remover_move_has_loc():
    """LPHIRemover creates Move statements with proper Loc."""
    scope = _build_simple_loop_scope()

    # Set a loc on the LPhi
    loop_head = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'loop_head':
            loop_head = blk
            break
    lphi = loop_head.collect_stms([LPhi])[0]
    object.__setattr__(lphi, 'loc', Loc('test.py', 10))

    LPHIRemover().process(scope)

    # Check that init Move has Loc with filename from LPhi and line 0
    entry_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'entry':
            entry_blk = blk
            break
    init_moves = [s for s in entry_blk.stms if isinstance(s, Move) and
                  isinstance(s.dst, Temp) and s.dst.name == 'i']
    assert len(init_moves) == 1
    assert init_moves[0].loc.filename == 'test.py'
    assert init_moves[0].loc.lineno == 0

    # Check that update Move in MStm has the original loc
    loop_body = loop_head.preds_loop[0]
    mstms = [s for s in loop_body.stms if isinstance(s, MStm)]
    assert len(mstms) == 1
    update_move = mstms[0].stms[0]
    assert update_move.loc.filename == 'test.py'
    assert update_move.loc.lineno == 10


def test_lphi_remover_no_loc():
    """LPHIRemover handles LPhi with no loc (None)."""
    scope = _build_simple_loop_scope()

    loop_head = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'loop_head':
            loop_head = blk
            break
    lphi = loop_head.collect_stms([LPhi])[0]
    # Set loc to None
    object.__setattr__(lphi, 'loc', None)

    LPHIRemover().process(scope)

    # Should not crash; init Move should have Loc('', 0)
    entry_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'entry':
            entry_blk = blk
            break
    init_moves = [s for s in entry_blk.stms if isinstance(s, Move) and
                  isinstance(s.dst, Temp) and s.dst.name == 'i']
    assert len(init_moves) == 1
    assert init_moves[0].loc.filename == ''
    assert init_moves[0].loc.lineno == 0

    # Update Move should also have Loc('', 0)
    loop_body = loop_head.preds_loop[0]
    mstms = [s for s in loop_body.stms if isinstance(s, MStm)]
    update_move = mstms[0].stms[0]
    assert update_move.loc.filename == ''
    assert update_move.loc.lineno == 0
