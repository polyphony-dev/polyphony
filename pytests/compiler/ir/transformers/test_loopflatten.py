"""Tests for LoopFlatten."""
from polyphony.compiler.ir.ir import Const, Temp, Move, CJump, BinOp, RelOp, LPhi, Jump, Ret, Expr, Ctx
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
from polyphony.compiler.ir.analysis.loopdetector import LoopInfoSetter, LoopDependencyDetector
from polyphony.compiler.ir.transformers.looptransformer import LoopFlatten
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_new_loop_flatten_no_pipeline():
    """LoopFlatten returns False when no pipeline loop exists."""
    setup_test()
    scope = Scope.create(None, 'FlatTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i_init', tags=set(), typ=Type.int())
    i_sym = scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    cond_sym = scope.add_sym('cond', tags=set(), typ=Type.bool())

    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    blk_entry.append_stm(Expr(Const(0)))  # guard from reduceblk
    blk_entry.append_stm(Jump(loop_head))

    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', [Temp('i_init'), Temp('i_upd')])
    object.__setattr__(i_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(i_lphi)
    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(10))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body, loop_exit))

    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    jmp = Jump(loop_head, typ='L')
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
    LoopDependencyDetector().process(scope)

    # No pipeline scheduling => flatten returns False
    result = LoopFlatten().process(scope)
    assert result is None or result is False or not result


def test_new_loop_flatten_class_exists():
    """LoopFlatten class can be imported and instantiated."""
    from polyphony.compiler.ir.transformers.looptransformer import LoopFlatten
    f = LoopFlatten()
    assert f is not None
