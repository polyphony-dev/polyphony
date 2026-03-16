"""Tests for NewDFGBuilder."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.scheduling.dataflow import (
    NewDFGBuilder,
    _is_move, _is_expr, _is_const, _is_temp,
    _is_call, _is_syscall, _is_mref, _is_mstore,
    _is_jump, _is_cjump, _is_mcjump, _is_ctrl_stm,
    _is_phi, _is_variable,
    _is_mem_read, _is_mem_write,
)
from polyphony.compiler.ir.scheduling.dataflow import DataFlowGraph
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src, scheduling='sequential'):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    name = list(parser.sources)[0]
    scope = env.scopes[name]
    for blk in scope.traverse_blocks():
        blk.synth_params['scheduling'] = scheduling
    return scope


def build_scope_with_loop(src, scheduling='sequential'):
    """Build scope and run LoopDetector so DFGBuilder can work."""
    scope = build_scope(src, scheduling)
    LoopDetector().process(scope)
    return scope


# --- Type dispatcher tests ---

def test_is_move_old_ir():
    """_is_move recognizes old IR MOVE."""
    m = MOVE(TEMP('x', Ctx.STORE), CONST(1))
    assert _is_move(m)


def test_is_move_not_expr():
    """_is_move rejects EXPR."""
    e = EXPR(CONST(1))
    assert not _is_move(e)


def test_is_expr_old_ir():
    """_is_expr recognizes old IR EXPR."""
    e = EXPR(CONST(1))
    assert _is_expr(e)


def test_is_const_old_ir():
    """_is_const recognizes old IR CONST."""
    assert _is_const(CONST(42))


def test_is_temp_old_ir():
    """_is_temp recognizes old IR TEMP."""
    assert _is_temp(TEMP('x', Ctx.LOAD))


def test_is_ctrl_stm_jump():
    """_is_ctrl_stm recognizes JUMP."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_scope', {'function'})
    from polyphony.compiler.ir.block import Block
    blk = Block(scope)
    j = JUMP(blk)
    assert _is_ctrl_stm(j)


def test_is_variable():
    """_is_variable recognizes both old and new IR variables."""
    assert _is_variable(TEMP('x', Ctx.LOAD))


def test_is_mem_read():
    """_is_mem_read detects MOVE with MREF src."""
    m = MOVE(TEMP('x', Ctx.STORE), MREF(TEMP('arr', Ctx.LOAD), CONST(0), Ctx.LOAD))
    assert _is_mem_read(m)


def test_is_mem_write():
    """_is_mem_write detects EXPR with MSTORE exp."""
    e = EXPR(MSTORE(TEMP('arr', Ctx.LOAD), CONST(0), CONST(1)))
    assert _is_mem_write(e)


def test_is_mem_read_not_move():
    """_is_mem_read returns False for non-MOVE."""
    e = EXPR(CONST(1))
    assert not _is_mem_read(e)


# --- DFG building tests ---

def test_dfg_simple_linear():
    """NewDFGBuilder creates DFG for linear block."""
    src = '''
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
'''
    scope = build_scope_with_loop(src)
    builder = NewDFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    assert dfg is not None
    assert isinstance(dfg, DataFlowGraph)
    assert len(dfg.nodes) >= 3


def test_dfg_has_defuse_edges():
    """NewDFGBuilder creates def-use edges between definitions and uses."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 10
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    builder = NewDFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    defuse_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'DefUse']
    assert len(defuse_edges) > 0, "Expected DefUse edges"


def test_dfg_source_nodes():
    """NewDFGBuilder identifies source nodes (constant assignments)."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    builder = NewDFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    assert len(dfg.src_nodes) > 0, "Expected source nodes"


def test_dfg_sequential_scheduling():
    """NewDFGBuilder adds seq edges for sequential scheduling."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y 20
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='sequential')
    builder = NewDFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    seq_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'Seq']
    assert len(seq_edges) > 0, "Expected Seq edges for sequential scheduling"


def test_is_constant_stm_move_const():
    """_is_constant_stm recognizes MOVE with CONST src."""
    builder = NewDFGBuilder()
    m = MOVE(TEMP('x', Ctx.STORE), CONST(42))
    assert builder._is_constant_stm(m)


def test_is_constant_stm_move_array():
    """_is_constant_stm recognizes MOVE with ARRAY src."""
    builder = NewDFGBuilder()
    m = MOVE(TEMP('x', Ctx.STORE), ARRAY([CONST(1)], True))
    assert builder._is_constant_stm(m)


def test_is_constant_stm_move_temp():
    """_is_constant_stm rejects MOVE with TEMP src."""
    builder = NewDFGBuilder()
    m = MOVE(TEMP('x', Ctx.STORE), TEMP('y', Ctx.LOAD))
    assert not builder._is_constant_stm(m)
