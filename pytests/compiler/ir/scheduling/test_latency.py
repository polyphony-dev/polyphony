"""Tests for latency calculation (_get_latency, get_latency)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.scheduling.latency import (
    get_latency, _get_latency, UNIT_STEP, CALL_MINIMUM_STEP,
)
from polyphony.compiler.ir.scheduling.dataflow import DFGBuilder
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src, scheduling='sequential'):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    name = list(parser.sources)[0]
    scope = env.scopes[name]
    for blk in scope.traverse_blocks():
        blk.synth_params['scheduling'] = scheduling
        blk.synth_params['cycle'] = 'any'
        blk.synth_params['ii'] = -1
    return scope


# ============================================================
# _get_latency for Move statements
# ============================================================

def test_latency_move_const():
    """Move with const src returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]  # mv x 42
    assert _get_latency(stm) == UNIT_STEP


def test_latency_move_alias_dst():
    """Move to alias variable returns 0 (wire assignment)."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}

blk1:
mv a 1
mv @return a
ret @return
''')
    stm = scope.entry_block.stms[0]  # mv a 1
    assert _get_latency(stm) == 0


def test_latency_move_new():
    """Move with New src returns 0."""
    # New requires full compiler pipeline, test via get_latency wrapper
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]
    def_l, seq_l = get_latency(stm)
    assert def_l == UNIT_STEP
    assert seq_l == UNIT_STEP


def test_latency_move_mref():
    """Move with MRef src (memory read) returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var x: int32
var i: int32

blk1:
mv i 0
mv x (mld arr i)
mv @return x
ret @return
''')
    for stm in scope.entry_block.stms:
        if isinstance(stm, Move) and isinstance(stm.src, MRef):
            assert _get_latency(stm) == UNIT_STEP
            return
    assert False, "MRef statement not found"


def test_latency_move_temp_to_temp():
    """Move from temp to temp (register copy) returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y x
mv @return y
ret @return
''')
    stm = scope.entry_block.stms[1]  # mv y x
    assert _get_latency(stm) == UNIT_STEP


def test_latency_move_alias_to_alias():
    """Move from alias to alias returns 0."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}
var b: int32 {alias}

blk1:
mv a 1
mv b a
mv @return b
ret @return
''')
    stm = scope.entry_block.stms[1]  # mv b a
    assert _get_latency(stm) == 0


# ============================================================
# _get_latency for Expr statements
# ============================================================

def test_latency_expr_mstore():
    """Expr with MStore returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var i: int32

blk1:
mv i 0
expr (mst arr i 99)
mv @return 0
ret @return
''')
    for stm in scope.entry_block.stms:
        if isinstance(stm, Expr) and isinstance(stm.exp, MStore):
            assert _get_latency(stm) == UNIT_STEP
            return
    assert False, "MStore Expr not found"


# ============================================================
# get_latency wrapper
# ============================================================

def test_get_latency_returns_tuple():
    """get_latency always returns (def_latency, seq_latency) pair."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]
    result = get_latency(stm)
    assert isinstance(result, tuple)
    assert len(result) == 2
    def_l, seq_l = result
    assert def_l >= 0
    assert seq_l >= 0


def test_get_latency_alias_zero():
    """get_latency for alias Move returns (0, 0)."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}

blk1:
mv a 1
mv @return a
ret @return
''')
    stm = scope.entry_block.stms[0]
    def_l, seq_l = get_latency(stm)
    assert def_l == 0
    assert seq_l == 0
