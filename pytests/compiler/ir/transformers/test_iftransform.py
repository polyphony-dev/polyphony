"""Tests for new IfTransformer and IfCondTransformer (ir-based)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.transformers.iftransform import IfTransformer, IfCondTransformer
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.irwriter import IrWriter
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def test_no_cjump_unchanged():
    """Blocks without CJUMP should not be affected."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv x 2
'''
    scope = build_scope(src)
    writer = IrWriter()
    before = [writer.write_stm(s) for s in scope.entry_block.stms]

    IfTransformer().process(scope)

    after = [writer.write_stm(s) for s in scope.entry_block.stms]
    assert before == after


def test_simple_cjump_unchanged():
    """A single CJUMP (no chained else-if) should remain unchanged."""
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
j exit

blk3:
mv x 2
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    blk1 = scope.entry_block

    IfTransformer().process(scope)

    # Still a CJUMP (not merged into MCJUMP because blk3 has >1 stm or not a CJUMP)
    last = blk1.stms[-1]
    assert isinstance(last, CJump)


def test_chained_cjump_to_mcjump():
    """Chained if-elif-else should be merged into MCJUMP.

    CFG: blk1 -cj(c1)-> blk2 (then)
                      -> else1 -cj(c2)-> blk3 (then)
                                      -> blk4 (else/final)
    """
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)
    scope.add_sym('c1', tags=set(), typ=Type.bool())
    scope.add_sym('c2', tags=set(), typ=Type.bool())
    scope.add_sym('x', tags=set(), typ=Type.int(32))

    blk1 = Block(scope, nametag='blk1')
    blk2 = Block(scope, nametag='blk2')
    else1 = Block(scope, nametag='else1')
    blk3 = Block(scope, nametag='blk3')
    blk4 = Block(scope, nametag='blk4')

    scope.set_entry_block(blk1)
    scope.set_exit_block(blk4)

    # blk1: cj c1 blk2 else1 (new IR in stms, post-switchover)
    cj1 = CJump(exp=Temp(name='c1'), true=blk2, false=else1, block=blk1)
    blk1.stms.append(cj1)
    blk1.connect(blk2)
    blk1.connect(else1)

    # else1: cj c2 blk3 blk4  (single CJUMP — should be merged)
    cj2 = CJump(exp=Temp(name='c2'), true=blk3, false=blk4, block=else1)
    else1.stms.append(cj2)
    else1.connect(blk3)
    else1.connect(blk4)

    # blk2, blk3, blk4: simple
    mv2 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1), block=blk2)
    blk2.stms.append(mv2)
    mv3 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=2), block=blk3)
    blk3.stms.append(mv3)
    mv4 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=3), block=blk4)
    blk4.stms.append(mv4)

    Block.set_order(blk1, 0)

    # Run new IfTransformer via adapter
    IfTransformer().process(scope)

    # blk1 should now end with MCJUMP instead of CJUMP
    last = blk1.stms[-1]
    assert isinstance(last, MCJump), f'Expected MCJUMP, got {type(last).__name__}'
    assert len(last.conds) == 3  # c1, c2, Const(1)
    assert len(last.targets) == 3  # blk2, blk3, blk4

    # else1 should be emptied
    assert else1.stms == []

    # Verify targets
    assert last.targets[0] is blk2
    assert last.targets[1] is blk3
    assert last.targets[2] is blk4

    # Verify succs/preds
    assert blk2 in blk1.succs
    assert blk3 in blk1.succs
    assert blk4 in blk1.succs


def test_empty_block_skipped():
    """Empty blocks should be skipped by _process_block."""
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)
    scope.add_sym('x', tags=set(), typ=Type.int(32))

    blk1 = Block(scope, nametag='blk1')
    blk2 = Block(scope, nametag='blk2')
    scope.set_entry_block(blk1)
    scope.set_exit_block(blk2)

    # blk1 has stms, blk2 is empty
    mv = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1), block=blk1)
    blk1.stms.append(mv)
    blk1.stms.append(Jump(target=blk2, block=blk1))
    blk1.connect(blk2)

    Block.set_order(blk1, 0)
    # Should not crash on empty blk2
    IfTransformer().process(scope)

    assert blk2.stms == []
    assert len(blk1.stms) == 2


def test_triple_chain_cjump():
    """Three-level chained if-elif-elif-else should be merged into MCJUMP with 4 branches.

    CFG: blk1 -cj(c1)-> t1
                       -> e1 -cj(c2)-> t2
                                     -> e2 -cj(c3)-> t3
                                                   -> t4 (else)
    """
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)
    scope.add_sym('c1', tags=set(), typ=Type.bool())
    scope.add_sym('c2', tags=set(), typ=Type.bool())
    scope.add_sym('c3', tags=set(), typ=Type.bool())
    scope.add_sym('x', tags=set(), typ=Type.int(32))

    blk1 = Block(scope, nametag='blk1')
    t1 = Block(scope, nametag='t1')
    e1 = Block(scope, nametag='e1')
    t2 = Block(scope, nametag='t2')
    e2 = Block(scope, nametag='e2')
    t3 = Block(scope, nametag='t3')
    t4 = Block(scope, nametag='t4')

    scope.set_entry_block(blk1)
    scope.set_exit_block(t4)

    # blk1: cj c1 t1 e1
    blk1.stms.append(CJump(exp=Temp(name='c1'), true=t1, false=e1, block=blk1))
    blk1.connect(t1)
    blk1.connect(e1)

    # e1: cj c2 t2 e2 (single CJUMP)
    e1.stms.append(CJump(exp=Temp(name='c2'), true=t2, false=e2, block=e1))
    e1.connect(t2)
    e1.connect(e2)

    # e2: cj c3 t3 t4 (single CJUMP)
    e2.stms.append(CJump(exp=Temp(name='c3'), true=t3, false=t4, block=e2))
    e2.connect(t3)
    e2.connect(t4)

    # target blocks: simple stms
    for blk in (t1, t2, t3, t4):
        blk.stms.append(Move(dst=Temp(name='x', ctx=Ctx.STORE),
                                 src=Const(value=0), block=blk))

    Block.set_order(blk1, 0)
    IfTransformer().process(scope)

    last = blk1.stms[-1]
    assert isinstance(last, MCJump)
    assert len(last.conds) == 4  # c1, c2, c3, Const(1)
    assert len(last.targets) == 4  # t1, t2, t3, t4
    assert isinstance(last.conds[-1], Const)
    assert last.conds[-1].value == 1


# ---- IfCondTransformer tests ----


def _build_mcjump_scope(n_conds):
    """Build a scope with one block ending in MCJUMP with n_conds conditions.

    Returns (scope, entry_block, mcjump, target_blocks).
    """
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)

    cond_names = [f'c{i}' for i in range(n_conds)]
    for name in cond_names:
        scope.add_sym(name, tags=set(), typ=Type.bool())
    scope.add_sym('x', tags=set(), typ=Type.int(32))

    blk1 = Block(scope, nametag='blk1')
    targets = [Block(scope, nametag=f't{i}') for i in range(n_conds + 1)]
    scope.set_entry_block(blk1)
    scope.set_exit_block(targets[-1])

    conds = [Temp(name=name) for name in cond_names]
    conds.append(Const(value=1))  # else branch

    mj = MCJump(conds=conds, targets=targets, block=blk1)
    blk1.stms.append(mj)
    for t in targets:
        blk1.connect(t)
        t.stms.append(Move(dst=Temp(name='x', ctx=Ctx.STORE),
                                src=Const(value=0), block=t))

    Block.set_order(blk1, 0)
    return scope, blk1, mj, targets


def test_ifcond_no_mcjump():
    """Blocks without MCJUMP should not be affected."""
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)
    scope.add_sym('x', tags=set(), typ=Type.int(32))

    blk1 = Block(scope, nametag='blk1')
    blk2 = Block(scope, nametag='blk2')
    scope.set_entry_block(blk1)
    scope.set_exit_block(blk2)

    blk1.stms.append(Move(dst=Temp(name='x', ctx=Ctx.STORE),
                               src=Const(value=1), block=blk1))
    blk1.stms.append(Jump(target=blk2, block=blk1))
    blk1.connect(blk2)

    Block.set_order(blk1, 0)
    IfCondTransformer().process(scope)

    # No changes
    assert len(blk1.stms) == 2
    assert isinstance(blk1.stms[-1], Jump)


def test_ifcond_empty_block():
    """Empty blocks should be skipped."""
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)

    blk1 = Block(scope, nametag='blk1')
    blk2 = Block(scope, nametag='blk2')
    scope.set_entry_block(blk1)
    scope.set_exit_block(blk2)

    blk1.stms.append(Jump(target=blk2, block=blk1))
    blk1.connect(blk2)
    # blk2 is empty

    Block.set_order(blk1, 0)
    IfCondTransformer().process(scope)
    assert blk2.stms == []


def test_ifcond_two_conds():
    """MCJUMP with 2 conditions + else should produce mutually exclusive conds.

    conds: [c0, Const(1)]  ->  [c0, !c0]
    First condition stays as-is (Temp), second becomes NOT(c0) which needs a Move.
    """
    scope, blk1, mj, targets = _build_mcjump_scope(1)

    IfCondTransformer().process(scope)

    # The MCJump should now have 2 conditions
    assert len(mj.conds) == 2
    # First cond is original Temp (stays as Temp)
    assert isinstance(mj.conds[0], Temp)
    assert mj.conds[0].name == 'c0'
    # Second cond should be a new condition temp (from the Move)
    assert isinstance(mj.conds[1], Temp)
    # A Move should have been inserted before the MCJUMP
    assert len(blk1.stms) >= 2
    assert isinstance(blk1.stms[-2], Move)


def test_ifcond_three_conds():
    """MCJUMP with 3 conditions + else should produce 4 mutually exclusive conds.

    conds: [c0, c1, Const(1)]
    ->  [c0, (!c0 && c1), (!c0 && !c1)]
    """
    scope, blk1, mj, targets = _build_mcjump_scope(2)

    IfCondTransformer().process(scope)

    assert len(mj.conds) == 3
    # First cond stays as Temp
    assert isinstance(mj.conds[0], Temp)
    assert mj.conds[0].name == 'c0'
    # Other conds are new condition temps (from Moves)
    assert isinstance(mj.conds[1], Temp)
    assert isinstance(mj.conds[2], Temp)

    # Two Moves should have been inserted before the MCJUMP
    # (cond 0 is a simple Temp, no Move needed; conds 1 and 2 need Moves)
    moves_before_mj = [s for s in blk1.stms[:-1] if isinstance(s, Move)]
    assert len(moves_before_mj) == 2


def test_ifcond_four_conds():
    """MCJUMP with 4 conditions + else produces deeply nested AND/NOT expressions."""
    scope, blk1, mj, targets = _build_mcjump_scope(3)

    IfCondTransformer().process(scope)

    assert len(mj.conds) == 4
    # All conds should be Temp references
    for c in mj.conds:
        assert isinstance(c, Temp)

    # 3 Moves should have been inserted (cond 0 stays as-is)
    moves_before_mj = [s for s in blk1.stms[:-1] if isinstance(s, Move)]
    assert len(moves_before_mj) == 3
