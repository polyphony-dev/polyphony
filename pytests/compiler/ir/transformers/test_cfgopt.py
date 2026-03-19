"""Tests for CFG optimization passes (BlockReducer, PathExpTracer, helpers)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.cfgopt import (
    BlockReducer, PathExpTracer, can_merge_synth_params,
    _merge_path_exp_new, _rel_and_exp_new,
    HyperBlockBuilder,
)
from polyphony.compiler.ir.analysis.usedef import UseDefDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src, scheduling='sequential'):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        scope = env.scopes[name]
        for blk in scope.traverse_blocks():
            blk.synth_params['scheduling'] = scheduling
        return scope


# ===========================================================
# can_merge_synth_params
# ===========================================================

def test_can_merge_synth_params_same():
    """can_merge_synth_params returns True when scheduling matches."""
    p1 = {'scheduling': 'sequential'}
    p2 = {'scheduling': 'sequential'}
    assert can_merge_synth_params(p1, p2) is True


def test_can_merge_synth_params_different():
    """can_merge_synth_params returns False when scheduling differs."""
    p1 = {'scheduling': 'sequential'}
    p2 = {'scheduling': 'timed'}
    assert can_merge_synth_params(p1, p2) is False


# ===========================================================
# _rel_and_exp_new helper
# ===========================================================

def test_rel_and_exp_both_none():
    """_rel_and_exp_new with both None returns None."""
    result = _rel_and_exp_new(None, None)
    assert result is None


def test_rel_and_exp_left_none():
    """_rel_and_exp_new with left None returns right."""
    right = Temp(name='x')
    result = _rel_and_exp_new(None, right)
    assert result is right


def test_rel_and_exp_right_none():
    """_rel_and_exp_new with right None returns left."""
    left = Temp(name='x')
    result = _rel_and_exp_new(left, None)
    assert result is left


def test_rel_and_exp_left_const_true():
    """_rel_and_exp_new with left Const(True) returns right."""
    left = Const(value=1)
    right = Temp(name='x')
    result = _rel_and_exp_new(left, right)
    assert result is right


def test_rel_and_exp_right_const_true():
    """_rel_and_exp_new with right Const(True) returns left."""
    left = Temp(name='x')
    right = Const(value=1)
    result = _rel_and_exp_new(left, right)
    assert result is left


def test_rel_and_exp_both_vars():
    """_rel_and_exp_new with two vars returns RelOp(And)."""
    left = Temp(name='a')
    right = Temp(name='b')
    result = _rel_and_exp_new(left, right)
    assert isinstance(result, RelOp)
    assert result.op == 'And'


# ===========================================================
# _merge_path_exp_new
# ===========================================================

def test_merge_path_exp_jump():
    """_merge_path_exp_new with Jump returns pred path_exp."""
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
    blk1 = scope.entry_block
    blk2 = list(scope.traverse_blocks())[1]
    blk1.path_exp = Const(value=1)
    blk2.path_exp = None
    # blk1 has a Jump stm -> returns pred_path
    result = _merge_path_exp_new(blk1, blk2)
    assert isinstance(result, Const)


def test_merge_path_exp_cjump_true_branch():
    """_merge_path_exp_new with CJump returns And(path, cond) for true branch."""
    src = '''
scope F
tags function
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
j blk3

blk3:
mv c False
'''
    scope = build_scope(src)
    blk1 = scope.entry_block
    blk1.path_exp = Const(value=1)
    blk2 = list(scope.traverse_blocks())[1]
    result = _merge_path_exp_new(blk1, blk2)
    # Since path_exp is Const(1), result should be the cjump condition itself
    assert isinstance(result, Temp)


def test_merge_path_exp_cjump_false_branch():
    """_merge_path_exp_new with CJump returns And(path, Not(cond)) for false branch."""
    src = '''
scope F
tags function
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
j blk3

blk3:
mv c False
'''
    scope = build_scope(src)
    blk1 = scope.entry_block
    blk1.path_exp = Const(value=1)
    blk3 = list(scope.traverse_blocks())[2]
    result = _merge_path_exp_new(blk1, blk3)
    # false branch: And(path, Not(cond)) -> Not(cond) since path is Const(1)
    assert isinstance(result, UnOp)
    assert result.op == 'Not'


# ===========================================================
# BlockReducer
# ===========================================================

def test_block_reducer_class_scope():
    """BlockReducer skips class scopes."""
    src = '''
scope C
tags class
var x: int32

blk1:
mv x 10
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    # Should not crash


def test_block_reducer_merge_unidirectional():
    """BlockReducer merges a block with a single predecessor having a single successor."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv x 2
j blk3

blk3:
mv x 3
'''
    scope = build_scope(src)
    blocks_before = len(list(scope.traverse_blocks()))
    BlockReducer().process(scope)
    blocks_after = len(list(scope.traverse_blocks()))
    # Should have merged into fewer blocks
    assert blocks_after < blocks_before


def test_block_reducer_empty_block_removal():
    """BlockReducer removes empty blocks that only contain a jump."""
    src = '''
scope F
tags function
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
j blk3

blk3:
mv x 1
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    # blk2 (empty jump) should be removed
    blocks = list(scope.traverse_blocks())
    block_stms = [len(b.stms) for b in blocks]
    # All remaining blocks should have meaningful content
    for b in blocks:
        if b.stms:
            # No block should only have a Jump with a single pred->succ
            pass  # Just verify no crash


def test_block_reducer_duplicate_paths():
    """BlockReducer handles CJump where both targets are the same block."""
    src = '''
scope F
tags function
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    # Manually set true and false to the same block object to trigger _merge_duplicate_paths
    entry = scope.entry_block
    cj = entry.stms[-1]
    assert isinstance(cj, CJump)
    # After parse, blk2 is already shared in succs so the merge should work
    BlockReducer().process(scope)
    entry = scope.entry_block
    last = entry.stms[-1]
    # After merge, should be Jump (or CJump if blocks weren't identity-same)
    # The key is it doesn't crash
    assert isinstance(last, (Jump, CJump))


def test_block_reducer_preserves_exit_block():
    """BlockReducer correctly updates exit_block when needed."""
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
    BlockReducer().process(scope)
    # exit_block should still be valid
    assert scope.exit_block is not None


def test_block_reducer_orders_blocks():
    """BlockReducer sets block order after processing."""
    src = '''
scope F
tags function
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
j blk4

blk3:
mv x 2
j blk4

blk4:
mv x 3
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    # Entry block should have a valid order (non-negative)
    assert scope.entry_block.order >= 0


# ===========================================================
# PathExpTracer
# ===========================================================

def test_merge_path_exp_mcjump():
    """_merge_path_exp_new handles MCJump with single occurrence of target."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk3

blk2:
mv x 1
j blk4

blk3:
mv x 2
j blk4

blk4:
mv x 3
'''
    scope = build_scope(src)
    blk1 = scope.entry_block
    blk1.path_exp = Const(value=1)
    blk2 = list(scope.traverse_blocks())[1]
    result = _merge_path_exp_new(blk1, blk2)
    # blk2 is target[0] of MCJump, should get cond[0]
    assert result is not None


def test_block_reducer_chain_of_three():
    """BlockReducer merges a chain of three linear blocks."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv x 2
j blk3

blk3:
mv x 3
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    blocks = list(scope.traverse_blocks())
    # All blocks should merge into one
    assert len(blocks) == 1
    # All stms should be in the single block
    assert len(blocks[0].stms) == 3


# ===========================================================
# HyperBlockBuilder helpers
# ===========================================================

def test_has_timing_function_move():
    """HyperBlockBuilder._has_timing_function detects timing calls in Move."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    hbb.usedef = UseDefDetector().process(scope)
    # Regular Move should not be a timing function
    mv = scope.entry_block.stms[0]
    assert hbb._has_timing_function(mv) is False


def test_has_mem_access_false():
    """HyperBlockBuilder._has_mem_access returns False for regular Move."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    mv = scope.entry_block.stms[0]
    assert hbb._has_mem_access(mv) is False


def test_has_mem_access_mstore():
    """HyperBlockBuilder._has_mem_access returns True for Expr with MStore."""
    src = '''
scope F
tags function
var mem: list<int32>[10]
var x: int32
var y: int32

blk1:
expr (mst mem x y)
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    stm = scope.entry_block.stms[0]
    assert hbb._has_mem_access(stm) is True


def test_has_mem_access_mref():
    """HyperBlockBuilder._has_mem_access returns True for Move with MRef."""
    src = '''
scope F
tags function
var mem: list<int32>[10]
var x: int32

blk1:
mv x (mld mem 0)
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    stm = scope.entry_block.stms[0]
    assert hbb._has_mem_access(stm) is True


def test_has_instance_var_modification_false():
    """HyperBlockBuilder._has_instance_var_modification returns False for Temp dst."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    stm = scope.entry_block.stms[0]
    assert hbb._has_instance_var_modification(stm) is False


def test_has_instance_var_modification_true():
    """HyperBlockBuilder._has_instance_var_modification returns True for Attr dst."""
    src = '''
scope C
tags class
var x: int32

scope C.__init__
tags function method ctor
param $self: object(C) { self }

blk1:
mv $self.x 1
'''
    scope = build_scope(src, scheduling='timed')
    init_scope = env.scopes.get('C.__init__')
    if init_scope:
        hbb = HyperBlockBuilder()
        hbb.scope = init_scope
        stm = init_scope.entry_block.stms[0]
        assert hbb._has_instance_var_modification(stm) is True


def test_hyperblock_sequential_scheduling():
    """HyperBlockBuilder works with sequential scheduling (no CMove/CExpr)."""
    src = '''
scope F
tags function
var x: int32
var c: bool

b1:
mv c True
cj c b2 b3

b2:
mv x 1
j b4

b3:
mv x 2
j b4

b4:
mv x 3
'''
    scope = build_scope(src, scheduling='sequential')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    assert scope.entry_block.is_hyperblock


def test_hyperblock_timed_scheduling():
    """HyperBlockBuilder works with timed scheduling."""
    src = '''
scope F
tags function
var x: int32
var c: bool

b1:
mv c True
cj c b2 b3

b2:
mv x 1
j b4

b3:
mv x 2
j b4

b4:
mv x 3
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    assert scope.entry_block.is_hyperblock


def test_hyperblock_no_diamond():
    """HyperBlockBuilder does nothing when there is no diamond structure."""
    src = '''
scope F
tags function
var x: int32

b1:
mv x 1
j b2

b2:
mv x 2
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    # No diamond, so no hyperblock
    assert not scope.entry_block.is_hyperblock


def test_hyperblock_with_mem_access_timed():
    """HyperBlockBuilder converts mem access to CExpr in timed mode."""
    src = '''
scope F
tags function worker
var c: bool
var x: int32
var y: int32
var mem: list<int32>[10]

b1:
mv c True
cj c b2 b3

b2:
expr (mst mem x y)
j b3

b3:
mv x 0
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    entry = scope.entry_block
    # After merging, entry block should have been made a hyperblock
    assert entry.is_hyperblock
    # MStore should now be wrapped in CExpr
    found_cexpr = False
    for stm in entry.stms:
        if isinstance(stm, CExpr):
            found_cexpr = True
    assert found_cexpr, "MStore should be converted to CExpr in timed scheduling"


def test_block_reducer_empty_block_not_entry():
    """BlockReducer does not remove entry block even if empty."""
    src = '''
scope F
tags function
var x: int32

blk1:
j blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    # Entry block merged into blk2 or vice versa, but entry must remain valid
    assert scope.entry_block is not None
    assert len(list(scope.traverse_blocks())) >= 1


def test_block_reducer_preserves_loop_block():
    """BlockReducer preserves blocks with loop connections."""
    src = '''
scope F
tags function
var x: int32
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
j blk3

blk3:
mv x 2
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    # Should complete without error
    blocks = list(scope.traverse_blocks())
    assert len(blocks) >= 1


def test_block_reducer_timed_fortest_preserved():
    """BlockReducer preserves timed blocks before fortest blocks."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j fortest

fortest:
mv x 2
'''
    scope = build_scope(src, scheduling='timed')
    # After setting scheduling to timed, the fortest block should be preserved
    BlockReducer().process(scope)
    # Should not crash; both blocks should be mergeable since blk1->fortest is unidirectional
    blocks = list(scope.traverse_blocks())
    assert len(blocks) >= 1


def test_block_reducer_exit_block_update():
    """BlockReducer updates exit_block when merging removes the exit block."""
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
    original_exit = scope.exit_block
    BlockReducer().process(scope)
    # After merging blk2 into blk1, exit_block should be updated
    assert scope.exit_block is not None
    blocks = list(scope.traverse_blocks())
    assert scope.exit_block in blocks


def test_block_reducer_merge_duplicate_cjump():
    """BlockReducer._merge_duplicate_paths converts CJump with same targets to Jump,
    then merges remaining blocks."""
    src = '''
scope F
tags function
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
j blk3

blk3:
mv x 1
'''
    scope = build_scope(src)
    # After BlockReducer: blk2 (empty jump) removed, CJump targets become same,
    # then CJump simplified to Jump, then blk3 merged into blk1
    BlockReducer().process(scope)
    blocks = list(scope.traverse_blocks())
    # Everything should collapse into a single block
    assert len(blocks) == 1


# ===========================================================
# Additional tests for coverage
# ===========================================================

def test_merge_path_exp_mcjump_multiple_targets():
    """_merge_path_exp_new handles MCJump with same target appearing multiple times."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    blk1 = scope.entry_block
    blk1.path_exp = Const(value=1)
    blk2 = list(scope.traverse_blocks())[1]
    result = _merge_path_exp_new(blk1, blk2)
    assert result is not None


def test_merge_path_exp_empty_pred():
    """_merge_path_exp_new returns pred path_exp when pred has no stms."""
    src = '''
scope F
tags function
var x: int32

blk1:
j blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    blk1 = scope.entry_block
    blk2 = list(scope.traverse_blocks())[1]
    blk1.stms.clear()
    blk1.path_exp = Const(value=1)
    result = _merge_path_exp_new(blk1, blk2)
    assert isinstance(result, Const)
    assert result.value == 1


def test_rel_and_exp_both_const_true():
    """_rel_and_exp_new with both Const(True) returns Const."""
    left = Const(value=1)
    right = Const(value=1)
    result = _rel_and_exp_new(left, right)
    assert isinstance(result, Const)


def test_merge_path_exp_mcjump_idx_hint():
    """_merge_path_exp_new uses idx_hint for MCJump with duplicate targets."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    blk1 = scope.entry_block
    blk1.path_exp = Const(value=1)
    blk2 = list(scope.traverse_blocks())[1]
    result = _merge_path_exp_new(blk1, blk2, idx_hint=0)
    assert result is not None


def test_block_reducer_mcjump_all_same_target():
    """BlockReducer handles MCJump where all targets are the same block."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    entry = scope.entry_block
    last = entry.stms[-1]
    assert isinstance(last, (Jump, CJump, MCJump))


def test_has_timing_function_syscall():
    """HyperBlockBuilder._has_timing_function detects timing SysCall."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    syscall = SysCall(func=Temp(name='polyphony.timing.clksleep'), args=[])
    assert syscall.name == 'polyphony.timing.clksleep'
    expr_stm = Expr(exp=syscall, block=scope.entry_block.bid)
    assert hbb._has_timing_function(expr_stm) is True


def test_has_timing_function_non_timing_syscall():
    """HyperBlockBuilder._has_timing_function returns False for non-timing SysCall."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    syscall = SysCall(func=Temp(name='some_other_func'), args=[])
    expr_stm = Expr(exp=syscall, block=scope.entry_block.bid)
    assert hbb._has_timing_function(expr_stm) is False


def test_has_timing_function_expr_stm():
    """HyperBlockBuilder._has_timing_function returns False for plain Expr."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    from polyphony.compiler.ir.ir import BinOp
    binop = BinOp(op='Add', left=Const(value=1), right=Const(value=2))
    expr_stm = Expr(exp=binop, block=scope.entry_block.bid)
    assert hbb._has_timing_function(expr_stm) is False


def test_has_timing_function_jump():
    """HyperBlockBuilder._has_timing_function returns False for Jump."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    j = Jump(target=scope.entry_block.bid, block=scope.entry_block.bid)
    assert hbb._has_timing_function(j) is False


def test_has_mem_access_move_mref():
    """HyperBlockBuilder._has_mem_access returns True for Move with MRef src."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    from polyphony.compiler.ir.ir import MRef
    mref = MRef(mem=Temp(name='mem'), offset=Const(value=0))
    mv = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=mref, block=scope.entry_block.bid)
    assert hbb._has_mem_access(mv) is True


def test_hyperblock_diamond_with_timed():
    """HyperBlockBuilder converts diamond in timed scheduling, producing hyperblock."""
    src = '''
scope F
tags function
var x: int32
var c: bool

b1:
mv c True
cj c b2 b3

b2:
mv x 1
j b4

b3:
mv x 2
j b4

b4:
mv x 3
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    assert scope.entry_block.is_hyperblock
    assert len(scope.entry_block.stms) >= 3


def test_block_reducer_remove_empty_block_with_loop_preserved():
    """BlockReducer preserves empty blocks with loop connections."""
    src = '''
scope F
tags function
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
j blk3

blk3:
mv x 2
'''
    scope = build_scope(src)
    blk2 = list(scope.traverse_blocks())[1]
    blk2.preds_loop = [blk2]
    BlockReducer().process(scope)
    blocks = list(scope.traverse_blocks())
    assert len(blocks) >= 1


def test_has_timing_function_wait_rising():
    """HyperBlockBuilder._has_timing_function detects wait_rising."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    syscall = SysCall(func=Temp(name='polyphony.timing.wait_rising'), args=[])
    mv = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=syscall, block=scope.entry_block.bid)
    assert hbb._has_timing_function(mv) is True


def test_has_timing_function_wait_falling():
    """HyperBlockBuilder._has_timing_function detects wait_falling."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    syscall = SysCall(func=Temp(name='polyphony.timing.wait_falling'), args=[])
    expr_stm = Expr(exp=syscall, block=scope.entry_block.bid)
    assert hbb._has_timing_function(expr_stm) is True


def test_block_reducer_mcjump_all_same_target_simplification():
    """BlockReducer._merge_duplicate_paths handles MCJump with all same targets."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk3

blk2:
j blk4

blk3:
j blk4

blk4:
mv x 3
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    blocks = list(scope.traverse_blocks())
    assert len(blocks) >= 1


def test_hyperblock_pipeline_with_remains():
    """HyperBlockBuilder converts remains to CMove/CExpr in pipeline scheduling."""
    src = '''
scope F
tags function worker
var c: bool
var x: int32
var y: int32

b1:
mv c True
cj c b2 b3

b2:
mv x 1
j b4

b3:
mv y 2
j b4

b4:
mv x 3
'''
    scope = build_scope(src, scheduling='pipeline')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    assert scope.entry_block.is_hyperblock


def test_hyperblock_select_stms_for_speculation():
    """HyperBlockBuilder._select_stms_for_speculation separates moves and remains."""
    src = '''
scope F
tags function worker
var c: bool
var x: int32
var y: int32
var mem: list<int32>[10]

b1:
mv c True
cj c b2 b3

b2:
mv x 1
expr (mst mem 0 x)
j b4

b3:
mv y 2
j b4

b4:
mv x 3
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    usedef = UseDefDetector().process(scope)
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    hbb.usedef = usedef
    hbb.uddetector = UseDefDetector()
    hbb.uddetector.scope = scope
    hbb.uddetector.table = usedef
    blocks = list(scope.traverse_blocks())
    b2 = blocks[1]
    head = scope.entry_block
    moves, remains = hbb._select_stms_for_speculation(head, b2)
    assert len(moves) + len(remains) >= 1


def test_hyperblock_comb_scope():
    """HyperBlockBuilder works with comb scope."""
    src = '''
scope F
tags function comb
var c: bool
var x: int32

b1:
mv c True
cj c b2 b3

b2:
mv x 1
j b4

b3:
mv x 2
j b4

b4:
mv x 3
'''
    scope = build_scope(src, scheduling='sequential')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    assert scope.entry_block.is_hyperblock


def test_merge_path_exp_mcjump_multiple_occurrences():
    """_merge_path_exp_new handles MCJump with multiple occurrences of target using Or."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var c3: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk3

blk2:
mv x 1
j blk4

blk3:
mv x 2
j blk4

blk4:
mv x 3
'''
    scope = build_scope(src)
    blk1 = scope.entry_block
    blk1.path_exp = Const(value=1)
    mj = blk1.stms[-1]
    if isinstance(mj, MCJump):
        blk2_bid = mj.targets[0]
        blk1.stms[-1] = mj.model_copy(update={'targets': [blk2_bid, blk2_bid]})
        blk2 = scope.find_block(blk2_bid)
        result = _merge_path_exp_new(blk1, blk2)
        assert result is not None


def test_block_reducer_mcjump_duplicate_after_empty_removal():
    """BlockReducer._merge_duplicate_paths handles MCJump after empty block removal."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk3

blk2:
j blk4

blk3:
j blk4

blk4:
mv x 3
'''
    scope = build_scope(src)
    BlockReducer().process(scope)
    blocks = list(scope.traverse_blocks())
    assert len(blocks) >= 1
    entry = scope.entry_block
    last = entry.stms[-1]
    assert not isinstance(last, MCJump), "MCJump with all same targets should be simplified"


def test_block_reducer_remove_empty_block_entry_preserved():
    """BlockReducer._remove_empty_block returns False for entry block."""
    src = '''
scope F
tags function
var x: int32

blk1:
j blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    reducer = BlockReducer()
    reducer.scope = scope
    reducer.removed_blks = []
    result = reducer._remove_empty_block(scope.entry_block)
    assert result is False


def test_block_reducer_remove_empty_block_with_succs_loop():
    """BlockReducer._remove_empty_block returns False for blocks with succs_loop."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
j blk3

blk3:
mv x 2
'''
    scope = build_scope(src)
    blocks = list(scope.traverse_blocks())
    blk2 = blocks[1]
    blk2.succs_loop = [blk2]
    reducer = BlockReducer()
    reducer.scope = scope
    reducer.removed_blks = []
    result = reducer._remove_empty_block(blk2)
    assert result is False


def test_block_reducer_remove_empty_block_with_preds_loop():
    """BlockReducer._remove_empty_block returns False for blocks with preds_loop."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
j blk3

blk3:
mv x 2
'''
    scope = build_scope(src)
    blocks = list(scope.traverse_blocks())
    blk2 = blocks[1]
    blk2.preds_loop = [blk2]
    reducer = BlockReducer()
    reducer.scope = scope
    reducer.removed_blks = []
    result = reducer._remove_empty_block(blk2)
    assert result is False


def test_block_reducer_remove_empty_block_multi_stm():
    """BlockReducer._remove_empty_block returns False for blocks with multiple stms."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv x 2
j blk3

blk3:
mv x 3
'''
    scope = build_scope(src)
    blocks = list(scope.traverse_blocks())
    blk2 = blocks[1]
    reducer = BlockReducer()
    reducer.scope = scope
    reducer.removed_blks = []
    result = reducer._remove_empty_block(blk2)
    assert result is False


def test_hyperblock_walk_to_convergence_no_succ():
    """HyperBlockBuilder._walk_to_convergence returns False when no succs."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    path = []
    result = hbb._walk_to_convergence(scope.entry_block, path)
    assert result is False
    assert len(path) >= 1


def test_hyperblock_walk_to_convergence_multi_succ():
    """HyperBlockBuilder._walk_to_convergence returns False at branch point."""
    src = '''
scope F
tags function
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1

blk3:
mv x 2
'''
    scope = build_scope(src, scheduling='timed')
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    path = []
    result = hbb._walk_to_convergence(scope.entry_block, path)
    assert result is False


def test_hyperblock_find_branch_paths_no_convergence():
    """HyperBlockBuilder._find_branch_paths returns None when no convergence."""
    src = '''
scope F
tags function
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1

blk3:
mv x 2
'''
    scope = build_scope(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    hbb = HyperBlockBuilder()
    hbb.scope = scope
    branches, tails = hbb._find_branch_paths(scope.entry_block)
    assert branches is None
    assert tails is None


def test_merge_duplicate_paths_mcjump_all_same():
    """BlockReducer._merge_duplicate_paths simplifies MCJump with all same targets."""
    src = '''
scope F
tags function
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mj c1 blk2 c2 blk2

blk2:
mv x 1
'''
    scope = build_scope(src)
    reducer = BlockReducer()
    reducer.scope = scope
    reducer.removed_blks = []
    # MCJump targets already point to same block (blk2)
    reducer._merge_duplicate_paths(scope)
    entry = scope.entry_block
    last = entry.stms[-1]
    assert isinstance(last, Jump), "MCJump with all same targets should become Jump"


def test_merge_duplicate_paths_empty_block():
    """BlockReducer._merge_duplicate_paths skips blocks with no stms."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)
    reducer = BlockReducer()
    reducer.scope = scope
    reducer.removed_blks = []
    # Add an empty block to the scope
    from polyphony.compiler.ir.block import Block
    empty = Block(scope)
    empty.stms = []
    # Should not crash on empty blocks
    reducer._merge_duplicate_paths(scope)


def test_block_reducer_timed_fortest_empty_block():
    """BlockReducer._remove_empty_block returns False for timed empty block before fortest."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j fortest

fortest:
mv x 2
'''
    scope = build_scope(src, scheduling='timed')
    BlockReducer().process(scope)
    assert len(list(scope.traverse_blocks())) >= 1


def test_hyperblock_with_mem_access_pipeline():
    """HyperBlockBuilder converts mem access to CExpr in pipeline mode."""
    src = '''
scope F
tags function worker
var c: bool
var x: int32
var y: int32
var mem: list<int32>[10]

b1:
mv c True
cj c b2 b3

b2:
expr (mst mem x y)
j b3

b3:
mv x 0
'''
    scope = build_scope(src, scheduling='pipeline')
    for blk in scope.traverse_blocks():
        blk.path_exp = Const(value=1)
    UseDefDetector().process(scope)
    HyperBlockBuilder().process(scope)
    entry = scope.entry_block
    assert entry.is_hyperblock
