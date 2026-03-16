"""Tests for NewHyperBlockBuilder (ir-based)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.transformers.cfgopt import NewHyperBlockBuilder
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.usedef import UseDefDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src, scheduling='sequential'):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        scope = env.scopes[name]
        for blk in scope.traverse_blocks():
            blk.synth_params['scheduling'] = scheduling
        return scope


def run_new(src, scheduling='timed'):
    """Run NewHyperBlockBuilder and return the result scope."""
    scope = build_scope(src, scheduling=scheduling)
    for blk in scope.traverse_blocks():
        blk.path_exp = new.Const(value=1)
    # UseDefDetector needs old IR; convert, run, convert back
    UseDefDetector().process(scope)
    NewHyperBlockBuilder().process(scope)
    return scope


def test_simple_diamond():
    """Simple diamond with only movable stms should be merged into hyperblock."""
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
    scope = run_new(src)
    assert scope.entry_block.is_hyperblock


def test_nested_diamond_with_mem_access():
    """Nested diamond with memory access - the bug case.

    The bug: when the inner diamond is merged, mstore becomes a CEXPR
    in the inner head. When the outer diamond is merged, the CEXPR's
    stm.block was stale because stms.insert did not update it.
    """
    src = '''
scope F
tags function worker
var we: bool
var cond2: bool
var x: int32
var y: int32
var z: int32
var mem: list<int32>[10]

b1:
mv we True
cj we ifthen2 b4

ifthen2:
mv cond2 True
cj cond2 ifthen3 b5

ifthen3:
expr (mst mem x y)
j b5

b5:
j b4

b4:
mv z 0
'''
    scope = run_new(src)
    assert scope.entry_block.is_hyperblock
    # Verify stms were merged into entry block
    assert len(scope.entry_block.stms) > 0


def test_stm_block_updated_after_speculation():
    """Verify stm.block is updated when stms move to the head block."""
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
    scope = run_new(src)
    entry = scope.entry_block
    for stm in entry.stms:
        assert stm.block is entry, (
            f"stm {stm} has block={stm.block.name}, expected {entry.name}"
        )
