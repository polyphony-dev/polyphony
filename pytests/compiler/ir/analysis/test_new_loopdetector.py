"""Tests for NewLoopInfoSetter and NewLoopDependencyDetector."""
from polyphony.compiler.ir.ir import Const, Temp, Move, CJump, BinOp, RelOp, LPhi, Jump, Ret, Ctx
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
from polyphony.compiler.ir.analysis.loopdetector import NewLoopInfoSetter, NewLoopDependencyDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def _make_simple_loop_scope():
    """Build a scope with a simple for-loop:

        blk_entry:
          i_init = 0
          x_init = 0
          jump loop_head

        loop_head:  (loop header)
          i = lphi(i_init, i_upd)
          x = lphi(x_init, x_upd)
          cond = (i < 10)
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
    scope = Scope.create(None, 'LoopTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    # Symbols
    i_init_sym = scope.add_sym('i_init', tags={'induction'}, typ=Type.int())
    i_sym = scope.add_sym('i', tags={'induction'}, typ=Type.int())
    i_upd_sym = scope.add_sym('i_upd', tags=set(), typ=Type.int())
    x_init_sym = scope.add_sym('x_init', tags=set(), typ=Type.int())
    x_sym = scope.add_sym('x', tags=set(), typ=Type.int())
    x_upd_sym = scope.add_sym('x_upd', tags=set(), typ=Type.int())
    cond_sym = scope.add_sym('cond', tags=set(), typ=Type.bool())

    # Blocks
    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    # blk_entry stms
    blk_entry.append_stm(Move(Temp('i_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Move(Temp('x_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Jump(loop_head))

    # loop_head stms
    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', [Temp('i_init'), Temp('i_upd')])
    object.__setattr__(i_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(i_lphi)

    x_lphi = LPhi(Temp('x', Ctx.STORE))
    object.__setattr__(x_lphi, 'args', [Temp('x_init'), Temp('x_upd')])
    object.__setattr__(x_lphi, 'ps', [Const(1), Const(1)])
    loop_head.append_stm(x_lphi)

    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(10))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body, loop_exit))

    # loop_body stms
    loop_body.append_stm(Move(Temp('x_upd', Ctx.STORE), BinOp('Add', Temp('x'), Temp('i'))))
    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    jmp = Jump(loop_head, typ='L')
    loop_body.append_stm(jmp)

    # loop_exit stms
    loop_exit.append_stm(Move(Temp('@return', Ctx.STORE), Temp('x')))
    loop_exit.append_stm(Ret(Temp('@return')))

    # Connect blocks
    blk_entry.succs = [loop_head]
    loop_head.preds = [blk_entry, loop_body]
    loop_head.preds_loop = [loop_body]
    loop_head.succs = [loop_body, loop_exit]
    loop_body.preds = [loop_head]
    loop_body.succs = [loop_head]
    loop_body.succs_loop = [loop_head]
    loop_exit.preds = [loop_head]

    Block.set_order(blk_entry, 0)
    return scope


def test_new_loop_info_setter_basic():
    """NewLoopInfoSetter sets counter, init, update on loop."""
    scope = _make_simple_loop_scope()
    LoopDetector().process(scope)
    NewLoopInfoSetter().process(scope)
    loops = list(scope.child_regions(scope.top_region()))
    assert len(loops) == 1
    loop = loops[0]
    assert loop.counter is not None
    assert loop.counter.name == 'i'
    assert loop.init is not None
    assert loop.update is not None
    assert loop.exits is not None


def test_new_loop_info_setter_counter_tag():
    """NewLoopInfoSetter adds loop_counter tag to counter symbol."""
    scope = _make_simple_loop_scope()
    LoopDetector().process(scope)
    NewLoopInfoSetter().process(scope)
    loops = list(scope.child_regions(scope.top_region()))
    loop = loops[0]
    assert loop.counter.is_loop_counter()


def test_new_loop_dependency_detector_basic():
    """NewLoopDependencyDetector sets outer_defs/outer_uses/inner_defs/inner_uses."""
    scope = _make_simple_loop_scope()
    LoopDetector().process(scope)
    NewLoopInfoSetter().process(scope)
    NewLoopDependencyDetector().process(scope)
    loops = list(scope.child_regions(scope.top_region()))
    assert len(loops) == 1
    loop = loops[0]
    assert loop.outer_defs is not None
    assert loop.outer_uses is not None
    assert loop.inner_defs is not None
    assert loop.inner_uses is not None


def test_new_loop_dependency_detector_outer_uses():
    """NewLoopDependencyDetector detects symbols used outside the loop."""
    scope = _make_simple_loop_scope()
    LoopDetector().process(scope)
    NewLoopInfoSetter().process(scope)
    NewLoopDependencyDetector().process(scope)
    loops = list(scope.child_regions(scope.top_region()))
    loop = loops[0]
    # x is defined in the loop head (lphi) and used in loop_exit (mv @return x)
    outer_use_names = {s.name for s in loop.outer_uses}
    assert 'x' in outer_use_names
