"""Tests for LoopFlatten."""
from polyphony.compiler.ir.ir import (
    Const, Temp, Move, CJump, BinOp, RelOp, UnOp,
    LPhi, Phi, Jump, Ret, Expr, Ctx,
)
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import (
    LoopDetector, LoopInfoSetter, LoopDependencyDetector,
)
from polyphony.compiler.ir.transformers.looptransformer import LoopFlatten
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def _build_simple_loop_scope():
    """Build a scope with a single loop (no pipeline, no nesting)."""
    setup_test()
    scope = Scope.create(None, 'LoopTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i_init', tags=set(), typ=Type.int())
    i_sym = scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    scope.add_sym('cond', tags={'condition'}, typ=Type.bool())

    blk_entry = Block(scope, nametag='entry')
    loop_head = Block(scope, nametag='loop_head')
    loop_body = Block(scope, nametag='loop_body')
    loop_exit = Block(scope, nametag='loop_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(loop_exit)

    blk_entry.append_stm(Move(Temp('i_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Jump(loop_head.bid))

    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', (Temp('i_init'), Temp('i_upd')))
    object.__setattr__(i_lphi, 'ps', (Const(1), Const(1)))
    loop_head.append_stm(i_lphi)
    loop_head.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(10))))
    loop_head.append_stm(CJump(Temp('cond'), loop_body.bid, loop_exit.bid))

    loop_body.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    loop_body.append_stm(Jump(loop_head.bid, typ='L'))

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


def _build_nested_loop_pipeline_scope():
    """Build a scope with a nested loop where the outer loop is pipeline-scheduled.

    Structure:
        entry -> outer_head -> outer_body (= inner_head) -> inner_body -> inner_head
                                                          -> inner_exit (= outer_continue) -> outer_head
                            -> outer_exit
    """
    setup_test()
    scope = Scope.create(None, 'NestedLoop', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())

    scope.add_sym('i_init', tags=set(), typ=Type.int())
    i_sym = scope.add_sym('i', tags={'induction'}, typ=Type.int())
    scope.add_sym('i_upd', tags=set(), typ=Type.int())
    scope.add_sym('j_init', tags=set(), typ=Type.int())
    j_sym = scope.add_sym('j', tags={'induction'}, typ=Type.int())
    scope.add_sym('j_upd', tags=set(), typ=Type.int())
    scope.add_sym('outer_cond', tags={'condition'}, typ=Type.bool())
    scope.add_sym('inner_cond', tags={'condition'}, typ=Type.bool())
    scope.add_sym('acc', tags=set(), typ=Type.int())
    scope.add_sym('acc_init', tags=set(), typ=Type.int())

    blk_entry = Block(scope, nametag='entry')
    outer_head = Block(scope, nametag='outer_head')
    inner_head = Block(scope, nametag='inner_head')
    inner_body = Block(scope, nametag='inner_body')
    inner_exit = Block(scope, nametag='inner_exit')
    outer_exit = Block(scope, nametag='outer_exit')

    scope.set_entry_block(blk_entry)
    scope.set_exit_block(outer_exit)

    # entry
    blk_entry.append_stm(Move(Temp('i_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Move(Temp('acc_init', Ctx.STORE), Const(0)))
    blk_entry.append_stm(Jump(outer_head.bid))

    # outer_head: i loop
    i_lphi = LPhi(Temp('i', Ctx.STORE))
    object.__setattr__(i_lphi, 'args', (Temp('i_init'), Temp('i_upd')))
    object.__setattr__(i_lphi, 'ps', (Const(1), Const(1)))
    outer_head.append_stm(i_lphi)
    outer_head.append_stm(Move(Temp('outer_cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(4))))
    outer_head.append_stm(CJump(Temp('outer_cond'), inner_head.bid, outer_exit.bid))

    # inner_head: j loop
    j_lphi = LPhi(Temp('j', Ctx.STORE))
    object.__setattr__(j_lphi, 'args', (Temp('j_init'), Temp('j_upd')))
    object.__setattr__(j_lphi, 'ps', (Const(1), Const(1)))
    inner_head.append_stm(j_lphi)
    inner_head.append_stm(Move(Temp('j_init', Ctx.STORE), Const(0)))
    inner_head.append_stm(Move(Temp('inner_cond', Ctx.STORE), RelOp('Lt', Temp('j'), Const(4))))
    inner_head.append_stm(CJump(Temp('inner_cond'), inner_body.bid, inner_exit.bid))

    # inner_body
    inner_body.append_stm(Move(Temp('acc', Ctx.STORE), BinOp('Add', Temp('acc'), Const(1))))
    inner_body.append_stm(Move(Temp('j_upd', Ctx.STORE), BinOp('Add', Temp('j'), Const(1))))
    inner_body.append_stm(Jump(inner_head.bid, typ='L'))

    # inner_exit (= outer loop continue)
    inner_exit.append_stm(Move(Temp('i_upd', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))))
    inner_exit.append_stm(Jump(outer_head.bid, typ='L'))

    # outer_exit
    outer_exit.append_stm(Move(Temp('@return', Ctx.STORE), Temp('acc')))
    outer_exit.append_stm(Ret(Temp('@return')))

    # Set path expressions (normally done by earlier passes)
    blk_entry.path_exp = Const(1)
    outer_head.path_exp = Const(1)
    inner_head.path_exp = Temp('outer_cond')
    inner_body.path_exp = RelOp('And', Temp('outer_cond'), Temp('inner_cond'))
    inner_exit.path_exp = RelOp('And', Temp('outer_cond'),
                                UnOp('Not', Temp('inner_cond')))
    outer_exit.path_exp = UnOp('Not', Temp('outer_cond'))

    # Wire up blocks
    blk_entry.succs = [outer_head]
    outer_head.preds = [blk_entry, inner_exit]
    outer_head.preds_loop = [inner_exit]
    outer_head.succs = [inner_head, outer_exit]
    inner_head.preds = [outer_head, inner_body]
    inner_head.preds_loop = [inner_body]
    inner_head.succs = [inner_body, inner_exit]
    inner_body.preds = [inner_head]
    inner_body.succs = [inner_head]
    inner_body.succs_loop = [inner_head]
    inner_exit.preds = [inner_head]
    inner_exit.succs = [outer_head]
    inner_exit.succs_loop = [outer_head]
    outer_exit.preds = [outer_head]

    Block.set_order(blk_entry, 0)
    LoopDetector().process(scope)
    LoopInfoSetter().process(scope)
    LoopDependencyDetector().process(scope)
    return scope


# ===========================================================
# LoopFlatten: class instantiation
# ===========================================================

def test_loop_flatten_class_exists():
    """LoopFlatten class can be imported and instantiated."""
    f = LoopFlatten()
    assert f is not None


# ===========================================================
# LoopFlatten: no pipeline
# ===========================================================

def test_loop_flatten_no_pipeline():
    """LoopFlatten returns False when no pipeline loop exists."""
    scope = _build_simple_loop_scope()
    result = LoopFlatten().process(scope)
    assert result is None or result is False or not result


# ===========================================================
# LoopFlatten: helper methods
# ===========================================================

def test_def_stm():
    """_def_stm returns the single defining statement for a symbol."""
    scope = _build_simple_loop_scope()
    from polyphony.compiler.ir.analysis.usedef import UseDefDetector
    lf = LoopFlatten()
    lf.scope = scope
    lf.usedef = UseDefDetector().process(scope)

    i_init_sym = scope.find_sym('i_init')
    stm = lf._def_stm(i_init_sym)
    assert isinstance(stm, Move)
    assert isinstance(stm.dst, Temp) and stm.dst.name == 'i_init'


def test_is_loop_head():
    """_is_loop_head returns True for blocks with loop predecessors."""
    scope = _build_simple_loop_scope()
    lf = LoopFlatten()

    # loop_head has preds_loop
    loop_head = None
    for blk in scope.traverse_blocks():
        if blk.preds_loop:
            loop_head = blk
            break
    assert loop_head is not None
    assert lf._is_loop_head(loop_head) is True

    # entry has no preds_loop
    assert lf._is_loop_head(scope.entry_block) is False


def test_move_stms():
    """_move_stms moves all stms (except last) from src to dst."""
    scope = _build_simple_loop_scope()
    lf = LoopFlatten()

    # Create two blocks
    src_blk = Block(scope, nametag='src')
    dst_blk = Block(scope, nametag='dst')

    mv1 = Move(Temp('x', Ctx.STORE), Const(1))
    mv2 = Move(Temp('y', Ctx.STORE), Const(2))
    jmp = Jump(dst_blk.bid)
    src_blk.stms = [mv1, mv2, jmp]
    dst_jmp = Jump(src_blk.bid)
    dst_blk.stms = [dst_jmp]

    lf._move_stms(src_blk, dst_blk)

    # src should only have its last stm (the jump)
    assert len(src_blk.stms) == 1
    assert src_blk.stms[0] is jmp

    # dst should have the moved stms before its last stm (block may be model_copy'd)
    assert len(dst_blk.stms) == 3
    assert dst_blk.stms[0] == mv1
    assert dst_blk.stms[1] == mv2
    assert dst_blk.stms[2] is dst_jmp


# ===========================================================
# LoopFlatten: pipeline nested loop
# ===========================================================

def test_loop_flatten_pipeline_nested():
    """LoopFlatten flattens a nested loop when outer is pipeline-scheduled."""
    scope = _build_nested_loop_pipeline_scope()

    # Mark the outer loop as pipeline
    top_region = scope.top_region()
    outer_loops = scope.child_regions(top_region)
    assert len(outer_loops) >= 1
    outer_loop = outer_loops.orders()[0]
    outer_loop.head.synth_params['scheduling'] = 'pipeline'

    result = LoopFlatten().process(scope)
    assert result is True

    # After flattening, inner loop head should have 'pipeline' scheduling
    inner_loops = scope.child_regions(outer_loop)
    if inner_loops:
        inner_loop = inner_loops.orders()[0]
        assert inner_loop.head.synth_params.get('scheduling') == 'pipeline'


def test_loop_flatten_pipeline_creates_init_flag():
    """LoopFlatten creates an init flag when flattening pipeline loop."""
    scope = _build_nested_loop_pipeline_scope()

    top_region = scope.top_region()
    outer_loops = scope.child_regions(top_region)
    outer_loop = outer_loops.orders()[0]
    outer_loop.head.synth_params['scheduling'] = 'pipeline'

    LoopFlatten().process(scope)

    # Check that an init symbol was created (by looking for 'init' in temp names)
    found_init = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, (LPhi, Phi)):
                sym = scope.find_sym(stm.var.name)
                if sym and 'init' in sym.name:
                    found_init = True
                    break
    assert found_init, "LoopFlatten should create an init flag symbol"


def test_loop_flatten_pipeline_creates_diamond():
    """LoopFlatten creates a diamond block structure (body + body_else)."""
    scope = _build_nested_loop_pipeline_scope()

    top_region = scope.top_region()
    outer_loops = scope.child_regions(top_region)
    outer_loop = outer_loops.orders()[0]
    outer_loop.head.synth_params['scheduling'] = 'pipeline'

    # Count blocks before
    blocks_before = list(scope.traverse_blocks())
    n_before = len(blocks_before)

    LoopFlatten().process(scope)

    # After flattening, new blocks should be added (body_else at minimum)
    blocks_after = list(scope.traverse_blocks())
    n_after = len(blocks_after)
    assert n_after > n_before, "Flattening should add new blocks (body_else)"


def test_loop_flatten_converts_inner_lphis():
    """LoopFlatten converts inner LPhis to Phis (psi) with condition guards."""
    scope = _build_nested_loop_pipeline_scope()

    top_region = scope.top_region()
    outer_loops = scope.child_regions(top_region)
    outer_loop = outer_loops.orders()[0]
    outer_loop.head.synth_params['scheduling'] = 'pipeline'

    LoopFlatten().process(scope)

    # After flattening, there should be Phi nodes (psi) in the inner loop region
    found_phi = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Phi) and not isinstance(stm, LPhi):
                found_phi = True
                break
    assert found_phi, "Flattening should create Phi (psi) nodes for induction variables"


def test_loop_flatten_no_nested_returns_false():
    """LoopFlatten returns False when the loop has no inner subloops even with pipeline."""
    scope = _build_simple_loop_scope()

    # Mark the loop as pipeline but it's a leaf (no inner loops)
    top_region = scope.top_region()
    loops = scope.child_regions(top_region)
    if loops:
        loop = loops.orders()[0]
        loop.head.synth_params['scheduling'] = 'pipeline'

    result = LoopFlatten().process(scope)
    # A leaf loop with pipeline but no children should not flatten
    assert result is None or result is False or not result
