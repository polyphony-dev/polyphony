"""Tests for restoring Block attributes after IrWriter/IrReader roundtrip.

Verifies that succs_loop/preds_loop and path_exp can be restored
after serialization/deserialization by re-running analysis passes.
"""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irwriter import IrWriter
from polyphony.compiler.ir.block import Block, detect_loop_edges
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
from polyphony.compiler.ir.transformers.cfgopt import PathExpTracer
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Tests: succs_loop / preds_loop restoration (manual block construction)
# ============================================================

def _build_simple_loop(scope):
    """Build: entry -> loop -> body -> loop (back), loop -> exit.

    Returns (entry, loop, body, exit) blocks.
    """
    entry = Block(scope, 'entry')
    loop = Block(scope, 'loop')
    body = Block(scope, 'body')
    exit_ = Block(scope, 'exit')
    scope.set_entry_block(entry)
    scope.set_exit_block(exit_)

    entry.connect(loop)
    loop.connect(body)
    loop.connect(exit_)
    body.connect_loop(loop)  # back edge

    entry.stms = [
        Move(Temp('i', Ctx.STORE), Const(0)),
        Jump(loop.bid),
    ]
    loop.stms = [
        Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('i'), Const(10))),
        CJump(Temp('cond'), body.bid, exit_.bid),
    ]
    body.stms = [
        Move(Temp('i', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))),
        Jump(loop.bid),
    ]
    exit_.stms = [Ret(Temp(Symbol.return_name))]

    Block.set_order(entry, 0)
    return entry, loop, body, exit_


def test_restore_simple_loop():
    """Back edge from body to loop head is detected by DFS."""
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function'}, 0)
    scope.add_sym('i', set(), typ=Type.int(32))
    scope.add_sym('cond', set(), typ=Type.bool())

    entry, loop, body, exit_ = _build_simple_loop(scope)

    # Verify original state
    assert loop in body.succs_loop
    assert body in loop.preds_loop

    # Simulate deserialization: clear loop edges
    for blk in scope.traverse_blocks():
        blk.succs_loop = []
        blk.preds_loop = []

    # Restore
    detect_loop_edges(scope)

    # Verify restored state
    assert loop in body.succs_loop, \
        f'Expected loop in body.succs_loop, got {body.succs_loop}'
    assert body in loop.preds_loop, \
        f'Expected body in loop.preds_loop, got {loop.preds_loop}'

    # Forward edges should NOT be in succs_loop
    assert entry.succs_loop == []
    assert loop.succs_loop == []


def test_restore_nested_loops():
    """Both outer and inner back edges are detected."""
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function'}, 0)
    scope.add_sym('i', set(), typ=Type.int(32))
    scope.add_sym('j', set(), typ=Type.int(32))
    scope.add_sym('c1', set(), typ=Type.bool())
    scope.add_sym('c2', set(), typ=Type.bool())

    entry = Block(scope, 'entry')
    outer = Block(scope, 'outer')
    inner_entry = Block(scope, 'ie')
    inner = Block(scope, 'inner')
    inner_body = Block(scope, 'ib')
    outer_cont = Block(scope, 'oc')
    exit_ = Block(scope, 'exit')
    scope.set_entry_block(entry)
    scope.set_exit_block(exit_)

    entry.connect(outer)
    outer.connect(inner_entry)
    outer.connect(exit_)
    inner_entry.connect(inner)
    inner.connect(inner_body)
    inner.connect(outer_cont)
    inner_body.connect_loop(inner)  # inner back edge
    outer_cont.connect_loop(outer)  # outer back edge

    entry.stms = [Move(Temp('i', Ctx.STORE), Const(0)), Jump(outer.bid)]
    outer.stms = [
        Move(Temp('c1', Ctx.STORE), RelOp('Lt', Temp('i'), Const(5))),
        CJump(Temp('c1'), inner_entry.bid, exit_.bid),
    ]
    inner_entry.stms = [Move(Temp('j', Ctx.STORE), Const(0)), Jump(inner.bid)]
    inner.stms = [
        Move(Temp('c2', Ctx.STORE), RelOp('Lt', Temp('j'), Const(10))),
        CJump(Temp('c2'), inner_body.bid, outer_cont.bid),
    ]
    inner_body.stms = [
        Move(Temp('j', Ctx.STORE), BinOp('Add', Temp('j'), Const(1))),
        Jump(inner.bid),
    ]
    outer_cont.stms = [
        Move(Temp('i', Ctx.STORE), BinOp('Add', Temp('i'), Const(1))),
        Jump(outer.bid),
    ]
    exit_.stms = [Ret(Temp(Symbol.return_name))]
    Block.set_order(entry, 0)

    # Clear and restore
    for blk in scope.traverse_blocks():
        blk.succs_loop = []
        blk.preds_loop = []

    detect_loop_edges(scope)

    # Inner back edge
    assert inner in inner_body.succs_loop
    assert inner_body in inner.preds_loop

    # Outer back edge
    assert outer in outer_cont.succs_loop
    assert outer_cont in outer.preds_loop


def test_set_order_after_restore():
    """Block.set_order() terminates and produces correct ordering after restore."""
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function'}, 0)
    scope.add_sym('i', set(), typ=Type.int(32))
    scope.add_sym('cond', set(), typ=Type.bool())

    entry, loop, body, exit_ = _build_simple_loop(scope)

    # Clear loop edges and reset order
    for blk in scope.traverse_blocks():
        blk.succs_loop = []
        blk.preds_loop = []
        blk.order = -1

    detect_loop_edges(scope)
    Block.set_order(entry, 0)

    # Verify topological ordering
    assert entry.order < loop.order
    assert loop.order < body.order
    assert loop.order < exit_.order


def test_loop_detector_after_restore():
    """LoopDetector runs successfully after loop edge restoration."""
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function'}, 0)
    scope.add_sym('i', set(), typ=Type.int(32))
    scope.add_sym('cond', set(), typ=Type.bool())

    entry, loop, body, exit_ = _build_simple_loop(scope)

    # Clear and restore
    for blk in scope.traverse_blocks():
        blk.succs_loop = []
        blk.preds_loop = []
        blk.order = -1

    detect_loop_edges(scope)
    Block.set_order(entry, 0)
    LoopDetector().process(scope)

    top_region = scope.top_region()
    assert top_region is not None
    children = scope.child_regions(top_region)
    assert len(children) == 1, f'Expected 1 loop region, got {len(children)}'


def test_no_loop_no_edges():
    """A scope without loops: restoration produces no loop edges."""
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function', 'returnable'}, 0)
    scope.return_type = Type.int(32)
    scope.add_sym('x', set(), typ=Type.int(32))
    scope.add_sym('cond', set(), typ=Type.bool())
    scope.add_return_sym(Type.int(32))

    entry = Block(scope, 'entry')
    then_ = Block(scope, 'then')
    else_ = Block(scope, 'else')
    exit_ = Block(scope, 'exit')
    scope.set_entry_block(entry)
    scope.set_exit_block(exit_)

    entry.connect(then_)
    entry.connect(else_)
    then_.connect(exit_)
    else_.connect(exit_)

    entry.stms = [
        Move(Temp('cond', Ctx.STORE), RelOp('Gt', Temp('x'), Const(0))),
        CJump(Temp('cond'), then_.bid, else_.bid),
    ]
    then_.stms = [Move(Temp('@return', Ctx.STORE), Const(1)), Jump(exit_.bid)]
    else_.stms = [Move(Temp('@return', Ctx.STORE), Const(0)), Jump(exit_.bid)]
    exit_.stms = [Ret(Temp('@return'))]
    Block.set_order(entry, 0)

    detect_loop_edges(scope)

    for blk in scope.traverse_blocks():
        assert blk.succs_loop == [], f'{blk.bid} has unexpected succs_loop'
        assert blk.preds_loop == [], f'{blk.bid} has unexpected preds_loop'


# ============================================================
# Tests: path_exp restoration
# ============================================================

def test_path_exp_if_else():
    """path_exp is computed correctly for if/else branches after restore."""
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function', 'returnable'}, 0)
    scope.return_type = Type.int(32)
    scope.add_sym('x', set(), typ=Type.int(32))
    scope.add_sym('cond', set(), typ=Type.bool())
    scope.add_return_sym(Type.int(32))

    entry = Block(scope, 'entry')
    then_ = Block(scope, 'then')
    else_ = Block(scope, 'else')
    exit_ = Block(scope, 'exit')
    scope.set_entry_block(entry)
    scope.set_exit_block(exit_)

    entry.connect(then_)
    entry.connect(else_)
    then_.connect(exit_)
    else_.connect(exit_)

    entry.stms = [
        Move(Temp('cond', Ctx.STORE), RelOp('Gt', Temp('x'), Const(0))),
        CJump(Temp('cond'), then_.bid, else_.bid),
    ]
    then_.stms = [Move(Temp('@return', Ctx.STORE), Const(1)), Jump(exit_.bid)]
    else_.stms = [Move(Temp('@return', Ctx.STORE), Const(0)), Jump(exit_.bid)]
    exit_.stms = [Ret(Temp('@return'))]
    Block.set_order(entry, 0)

    LoopDetector().process(scope)
    PathExpTracer().process(scope)

    assert then_.path_exp is not None, 'then block should have path_exp'
    assert else_.path_exp is not None, 'else block should have path_exp'

    writer = IrWriter()
    then_exp = writer.write_exp(then_.path_exp)
    else_exp = writer.write_exp(else_.path_exp)
    assert then_exp != else_exp, \
        f'then and else should have different path_exp: {then_exp} vs {else_exp}'


def test_path_exp_with_loop():
    """path_exp is computed for loop body and exit after restore."""
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function'}, 0)
    scope.add_sym('i', set(), typ=Type.int(32))
    scope.add_sym('cond', set(), typ=Type.bool())

    entry, loop, body, exit_ = _build_simple_loop(scope)

    # Clear loop edges, restore, then compute path_exp
    for blk in scope.traverse_blocks():
        blk.succs_loop = []
        blk.preds_loop = []
        blk.order = -1

    detect_loop_edges(scope)
    Block.set_order(entry, 0)
    LoopDetector().process(scope)
    PathExpTracer().process(scope)

    assert body.path_exp is not None, 'loop body should have path_exp'
    assert exit_.path_exp is not None, 'exit block should have path_exp'


def _normalize_path_exp(exp_str):
    """Normalize condition symbol names (@cNN) to positional placeholders."""
    import re
    if exp_str is None:
        return None
    counter = [0]
    mapping = {}

    def replacer(m):
        name = m.group(0)
        if name not in mapping:
            mapping[name] = f'@c_{counter[0]}'
            counter[0] += 1
        return mapping[name]

    return re.sub(r'@c\d+', replacer, exp_str)


def test_path_exp_roundtrip_matches():
    """path_exp after clear + restore matches the originally computed value.

    Condition symbol names (e.g., @c63) use a global counter so exact names
    differ between runs. We normalize them before comparison.
    """
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'F', {'function', 'returnable'}, 0)
    scope.return_type = Type.int(32)
    scope.add_sym('x', set(), typ=Type.int(32))
    scope.add_sym('cond', set(), typ=Type.bool())
    scope.add_return_sym(Type.int(32))

    entry = Block(scope, 'entry')
    then_ = Block(scope, 'then')
    else_ = Block(scope, 'else')
    exit_ = Block(scope, 'exit')
    scope.set_entry_block(entry)
    scope.set_exit_block(exit_)

    entry.connect(then_)
    entry.connect(else_)
    then_.connect(exit_)
    else_.connect(exit_)

    entry.stms = [
        Move(Temp('cond', Ctx.STORE), RelOp('Gt', Temp('x'), Const(0))),
        CJump(Temp('cond'), then_.bid, else_.bid),
    ]
    then_.stms = [Move(Temp('@return', Ctx.STORE), Const(1)), Jump(exit_.bid)]
    else_.stms = [Move(Temp('@return', Ctx.STORE), Const(0)), Jump(exit_.bid)]
    exit_.stms = [Ret(Temp('@return'))]
    Block.set_order(entry, 0)

    # Compute original path_exp
    LoopDetector().process(scope)
    PathExpTracer().process(scope)

    writer = IrWriter()
    orig_then = _normalize_path_exp(
        writer.write_exp(then_.path_exp) if then_.path_exp else None)
    orig_else = _normalize_path_exp(
        writer.write_exp(else_.path_exp) if else_.path_exp else None)

    # Clear all computed state
    for blk in scope.traverse_blocks():
        blk.path_exp = None
        blk.succs_loop = []
        blk.preds_loop = []
        blk.order = -1
    scope.reset_loop_tree()

    # Remove condition symbols added by PathExpTracer
    cond_syms = [n for n in scope.symbols if n.startswith('!cond')]
    for n in cond_syms:
        del scope.symbols[n]
    # Also remove the Move stms that PathExpTracer inserted
    for blk in scope.traverse_blocks():
        blk.stms = [s for s in blk.stms if not (
            isinstance(s, Move) and isinstance(s.dst, Temp)
            and s.dst.name.startswith('!cond')
        )]

    # Restore
    detect_loop_edges(scope)
    Block.set_order(entry, 0)
    LoopDetector().process(scope)
    PathExpTracer().process(scope)

    restored_then = _normalize_path_exp(
        writer.write_exp(then_.path_exp) if then_.path_exp else None)
    restored_else = _normalize_path_exp(
        writer.write_exp(else_.path_exp) if else_.path_exp else None)

    assert orig_then == restored_then, \
        f'then path_exp mismatch: {orig_then} vs {restored_then}'
    assert orig_else == restored_else, \
        f'else path_exp mismatch: {orig_else} vs {restored_else}'
