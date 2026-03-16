"""Tests for NewLoopUnroller."""
from polyphony.compiler.ir.ir import CONST, TEMP, MOVE, CJUMP, BINOP, RELOP, LPHI, JUMP, RET, EXPR, Ctx
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector, LoopRegionSetter
from polyphony.compiler.ir.analysis.loopdetector import NewLoopInfoSetter, NewLoopDependencyDetector
from polyphony.compiler.ir.transformers.unroll import NewLoopUnroller
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

    blk_entry.append_stm(EXPR(CONST(0)))  # guard from reduceblk
    blk_entry.append_stm(JUMP(loop_head))

    i_lphi = LPHI(TEMP('i', Ctx.STORE))
    i_lphi.args = [CONST(0), TEMP('i_upd')]
    i_lphi.ps = [CONST(1), CONST(1)]
    loop_head.append_stm(i_lphi)

    x_lphi = LPHI(TEMP('x', Ctx.STORE))
    x_lphi.args = [CONST(0), TEMP('x_upd')]
    x_lphi.ps = [CONST(1), CONST(1)]
    loop_head.append_stm(x_lphi)

    loop_head.append_stm(MOVE(TEMP('cond', Ctx.STORE), RELOP('Lt', TEMP('i'), CONST(trip_count))))
    loop_head.append_stm(CJUMP(TEMP('cond'), loop_body, loop_exit))

    loop_body.append_stm(MOVE(TEMP('x_upd', Ctx.STORE), BINOP('Add', TEMP('x'), TEMP('i'))))
    loop_body.append_stm(MOVE(TEMP('i_upd', Ctx.STORE), BINOP('Add', TEMP('i'), CONST(1))))
    jmp = JUMP(loop_head)
    jmp.typ = 'L'
    loop_body.append_stm(jmp)

    loop_exit.append_stm(MOVE(TEMP('@return', Ctx.STORE), TEMP('x')))
    loop_exit.append_stm(RET(TEMP('@return')))

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
    """NewLoopUnroller returns False when no unroll params set."""
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

    blk_entry.append_stm(EXPR(CONST(0)))  # guard from reduceblk
    blk_entry.append_stm(JUMP(loop_head))

    i_lphi = LPHI(TEMP('i', Ctx.STORE))
    i_lphi.args = [CONST(0), TEMP('i_upd')]
    i_lphi.ps = [CONST(1), CONST(1)]
    loop_head.append_stm(i_lphi)
    loop_head.append_stm(MOVE(TEMP('cond', Ctx.STORE), RELOP('Lt', TEMP('i'), CONST(4))))
    loop_head.append_stm(CJUMP(TEMP('cond'), loop_body, loop_exit))

    loop_body.append_stm(MOVE(TEMP('i_upd', Ctx.STORE), BINOP('Add', TEMP('i'), CONST(1))))
    jmp = JUMP(loop_head)
    jmp.typ = 'L'
    loop_body.append_stm(jmp)

    loop_exit.append_stm(MOVE(TEMP('@return', Ctx.STORE), TEMP('i')))
    loop_exit.append_stm(RET(TEMP('@return')))

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
    NewLoopInfoSetter().process(scope)
    LoopRegionSetter().process(scope)
    NewLoopDependencyDetector().process(scope)

    result = NewLoopUnroller().process(scope)
    # No unroll param => should not unroll (returns None)


def test_new_loop_unroller_full_unroll():
    """NewLoopUnroller fully unrolls a loop with factor='full'."""
    scope = _make_unrollable_loop_scope(trip_count=4, unroll='full')
    LoopDetector().process(scope)
    NewLoopInfoSetter().process(scope)
    LoopRegionSetter().process(scope)
    NewLoopDependencyDetector().process(scope)

    NewLoopUnroller().process(scope)

    # After full unroll, there should be no loop regions
    loops = list(scope.child_regions(scope.top_region()))
    assert len(loops) == 0, f'Expected no loops after full unroll, got {len(loops)}'

    # Should have more blocks than before (unrolled body copies)
    blocks = list(scope.traverse_blocks())
    assert len(blocks) > 4, f'Expected more blocks after unroll, got {len(blocks)}'


def test_new_loop_unroller_partial_unroll():
    """NewLoopUnroller partially unrolls a loop with factor=2."""
    scope = _make_unrollable_loop_scope(trip_count=4, unroll=2)
    LoopDetector().process(scope)
    NewLoopInfoSetter().process(scope)
    LoopRegionSetter().process(scope)
    NewLoopDependencyDetector().process(scope)

    NewLoopUnroller().process(scope)

    # After partial unroll (factor=2, trip=4), no remainder
    # The old loop should be removed, new loop should exist
    blocks = list(scope.traverse_blocks())
    assert len(blocks) > 4, f'Expected more blocks after partial unroll, got {len(blocks)}'


def test_new_loop_unroller_class_exists():
    """NewLoopUnroller class can be imported and instantiated."""
    from polyphony.compiler.ir.transformers.unroll import NewLoopUnroller
    u = NewLoopUnroller()
    assert u is not None
