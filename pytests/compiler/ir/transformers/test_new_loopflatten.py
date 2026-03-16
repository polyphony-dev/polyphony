"""Tests for NewLoopFlatten."""
from polyphony.compiler.ir.ir import CONST, TEMP, MOVE, CJUMP, BINOP, RELOP, LPHI, JUMP, RET, EXPR, Ctx
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
from polyphony.compiler.ir.analysis.loopdetector import NewLoopInfoSetter, NewLoopDependencyDetector
from polyphony.compiler.ir.transformers.looptransformer import NewLoopFlatten
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_new_loop_flatten_no_pipeline():
    """NewLoopFlatten returns False when no pipeline loop exists."""
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

    blk_entry.append_stm(EXPR(CONST(0)))  # guard from reduceblk
    blk_entry.append_stm(JUMP(loop_head))

    i_lphi = LPHI(TEMP('i', Ctx.STORE))
    i_lphi.args = [TEMP('i_init'), TEMP('i_upd')]
    i_lphi.ps = [CONST(1), CONST(1)]
    loop_head.append_stm(i_lphi)
    loop_head.append_stm(MOVE(TEMP('cond', Ctx.STORE), RELOP('Lt', TEMP('i'), CONST(10))))
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
    NewLoopDependencyDetector().process(scope)

    # No pipeline scheduling => flatten returns False
    result = NewLoopFlatten().process(scope)
    assert result is None or result is False or not result


def test_new_loop_flatten_class_exists():
    """NewLoopFlatten class can be imported and instantiated."""
    from polyphony.compiler.ir.transformers.looptransformer import NewLoopFlatten
    f = NewLoopFlatten()
    assert f is not None
