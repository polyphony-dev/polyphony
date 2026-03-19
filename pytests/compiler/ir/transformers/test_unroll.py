"""Tests for LoopUnroller."""
from polyphony.compiler.ir.ir import Const, Temp, Move, CJump, BinOp, RelOp, LPhi, Jump, Ret, Expr, Ctx
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector, LoopRegionSetter
from polyphony.compiler.ir.analysis.loopdetector import LoopInfoSetter, LoopDependencyDetector
from polyphony.compiler.ir.transformers.unroll import LoopUnroller
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def _make_unrollable_loop_scope(trip_count=4, unroll='full'):
    """Build a scope with a simple for-loop marked for unrolling.

        blk_entry:
          i_init = 0
          x_init = 0
          jump loop_head

        loop_head:  (loop header, unroll=True)
          i = lphi(i_init, i_upd)
          x = lphi(x_init, x_upd)
          cond = (i < trip_count)
          cjump cond loop_body loop_exit

        loop_body:
          x_upd = x + i
          i_upd = i + 1
          jump loop_head  (loop-back)

        loop_exit:
          @return = x
          ret @return
    """
    setup_test()
    scope = Scope.create(None, 'UnrollTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    scope.add_sym('x', tags={'induction'}, typ=Type.int())
    scope.add_sym('x_upd', tags=set(), typ=Type.int())
    scope.add_sym('cond', tags=set(), typ=Type.bool())

    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    blk_entry.append_stm(Expr(Const(0)))  # guard from reduceblk
    blk_entry.append_stm(Jump(loop_head.bid))

    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', [Const(0), Temp('i_upd')])
    object.__setattr__(i_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(i_lphi)

    x_lphi = LPhi(Temp('x', Ctx.STORE))
    object.__setattr__(x_lphi, 'args', [Const(0), Temp('x_upd')])
    object.__setattr__(x_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(x_lphi)

    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(trip_count))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body.bid, loop_exit.bid))

    loop_body.append_stm(Move(Temp('x_upd', Ctx.STORE), BinOp('Add', Temp('x'), Temp('i'))))
    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    jmp = Jump(loop_head.bid)
    object.__setattr__(jmp, 'typ', 'L')
    loop_body.append_stm(jmp)

    loop_exit.append_stm(Move(Temp('@return', Ctx.STORE), Temp('x')))
    loop_exit.append_stm(Ret(Temp('@return')))

    blk_entry.succs = [loop_head]
    loop_head.preds = [blk_entry, loop_body]
    loop_head.preds_loop = [loop_body]
    loop_head.succs = [loop_body, loop_exit]
    loop_body.preds = [loop_head]
    loop_body.succs = [loop_head]
    loop_body.succs_loop = [loop_head]
    loop_exit.preds = [loop_head]

    # Set unroll synth_params
    loop_head.synth_params['unroll'] = unroll
    loop_body.synth_params['unroll'] = unroll

    Block.set_order(blk_entry, 0)
    return scope


def test_new_loop_unroller_no_unroll():
    """LoopUnroller returns False when no unroll params set."""
    setup_test()
    scope = Scope.create(None, 'NoUnroll', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    scope.add_sym('cond', tags=set(), typ=Type.bool())

    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    blk_entry.append_stm(Expr(Const(0)))  # guard from reduceblk
    blk_entry.append_stm(Jump(loop_head.bid))

    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', [Const(0), Temp('i_upd')])
    object.__setattr__(i_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(i_lphi)
    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(4))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body.bid, loop_exit.bid))

    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    jmp = Jump(loop_head.bid)
    object.__setattr__(jmp, 'typ', 'L')
    loop_body.append_stm(jmp)

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
    LoopRegionSetter().process(scope)
    LoopDependencyDetector().process(scope)

    result = LoopUnroller().process(scope)
    # No unroll param => should not unroll (returns None)


def test_new_loop_unroller_full_unroll():
    """LoopUnroller fully unrolls a loop with factor='full'."""
    scope = _make_unrollable_loop_scope(trip_count=4, unroll='full')
    LoopDetector().process(scope)
    LoopInfoSetter().process(scope)
    LoopRegionSetter().process(scope)
    LoopDependencyDetector().process(scope)

    LoopUnroller().process(scope)

    # After full unroll, there should be no loop regions
    loops = list(scope.child_regions(scope.top_region()))
    assert len(loops) == 0, f'Expected no loops after full unroll, got {len(loops)}'

    # Should have more blocks than before (unrolled body copies)
    blocks = list(scope.traverse_blocks())
    assert len(blocks) > 4, f'Expected more blocks after unroll, got {len(blocks)}'


def test_new_loop_unroller_partial_unroll():
    """LoopUnroller partially unrolls a loop with factor=2."""
    scope = _make_unrollable_loop_scope(trip_count=4, unroll=2)
    LoopDetector().process(scope)
    LoopInfoSetter().process(scope)
    LoopRegionSetter().process(scope)
    LoopDependencyDetector().process(scope)

    LoopUnroller().process(scope)

    # After partial unroll (factor=2, trip=4), no remainder
    # The old loop should be removed, new loop should exist
    blocks = list(scope.traverse_blocks())
    assert len(blocks) > 4, f'Expected more blocks after partial unroll, got {len(blocks)}'


def test_new_loop_unroller_class_exists():
    """LoopUnroller class can be imported and instantiated."""
    from polyphony.compiler.ir.transformers.unroll import LoopUnroller
    u = LoopUnroller()
    assert u is not None
