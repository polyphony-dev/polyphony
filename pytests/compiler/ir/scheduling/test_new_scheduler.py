"""Tests for NewScheduler and latency."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.scheduling.dataflow import NewDFGBuilder
from polyphony.compiler.ir.scheduling.scheduler import (
    NewScheduler, NewResourceExtractor,
)
from polyphony.compiler.ir.scheduling.latency import (
    get_latency, UNIT_STEP, CALL_MINIMUM_STEP,
)
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
        blk.synth_params['cycle'] = 'any'
        blk.synth_params['ii'] = -1
    return scope


def build_scope_with_loop(src, scheduling='sequential'):
    """Build scope and run LoopDetector so DFGBuilder can work."""
    scope = build_scope(src, scheduling)
    LoopDetector().process(scope)
    return scope


def test_scheduler_simple():
    """NewScheduler schedules a simple function."""
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
    NewDFGBuilder().process(scope)
    NewScheduler().schedule(scope)

    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0, f"Node not scheduled: {node}"
        assert node.end >= node.begin, f"Node end < begin: {node}"


def test_scheduler_sets_asap_latency():
    """NewScheduler sets scope.asap_latency."""
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
    NewDFGBuilder().process(scope)
    NewScheduler().schedule(scope)

    assert scope.asap_latency >= CALL_MINIMUM_STEP


def test_scheduler_priorities():
    """NewScheduler assigns priority to nodes."""
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
    scope = build_scope_with_loop(src)
    NewDFGBuilder().process(scope)
    NewScheduler().schedule(scope)

    dfg = scope.top_dfg
    priorities = [n.priority for n in dfg.nodes]
    assert any(p >= 0 for p in priorities), "Expected nodes with priority >= 0"


def test_latency_move_const():
    """get_latency returns UNIT_STEP for simple MOVE."""
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
    scope = build_scope(src)
    blk = scope.entry_block
    stm = blk.stms[0]
    def_l, seq_l = get_latency(stm)
    assert def_l == UNIT_STEP
    assert seq_l == UNIT_STEP


def test_resource_extractor():
    """NewResourceExtractor can visit IR without errors."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x (+ 1 2)
mv y x
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    NewDFGBuilder().process(scope)

    extractor = NewResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)

    assert len(extractor.ops) > 0, "Expected operations to be extracted"


def test_scheduler_skips_namespace():
    """NewScheduler skips namespace scopes."""
    src = '''
scope ns
tags namespace
'''
    scope = build_scope(src)
    NewScheduler().schedule(scope)


def test_scheduler_skips_class():
    """NewScheduler skips class scopes."""
    src = '''
scope C
tags class
'''
    scope = build_scope(src)
    NewScheduler().schedule(scope)
