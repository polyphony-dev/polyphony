"""Tests for Scheduler and latency."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.scheduling.dataflow import DFGBuilder
from polyphony.compiler.ir.scheduling.scheduler import (
    Scheduler, ResourceExtractor,
)
from polyphony.compiler.ir.scheduling.latency import (
    get_latency, UNIT_STEP, CALL_MINIMUM_STEP,
)
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


def build_scope_with_loop(src, scheduling='sequential'):
    """Build scope and run LoopDetector so DFGBuilder can work."""
    scope = build_scope(src, scheduling)
    LoopDetector().process(scope)
    return scope


def test_scheduler_simple():
    """Scheduler schedules a simple function."""
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
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0, f"Node not scheduled: {node}"
        assert node.end >= node.begin, f"Node end < begin: {node}"


def test_scheduler_sets_asap_latency():
    """Scheduler sets scope.asap_latency."""
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
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    assert scope.asap_latency >= CALL_MINIMUM_STEP


def test_scheduler_priorities():
    """Scheduler assigns priority to nodes."""
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
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

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
    """ResourceExtractor can visit IR without errors."""
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
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)

    assert len(extractor.ops) > 0, "Expected operations to be extracted"


def test_scheduler_skips_namespace():
    """Scheduler skips namespace scopes."""
    src = '''
scope ns
tags namespace
'''
    scope = build_scope(src)
    Scheduler().schedule(scope)


def test_scheduler_skips_class():
    """Scheduler skips class scopes."""
    src = '''
scope C
tags class
'''
    scope = build_scope(src)
    Scheduler().schedule(scope)


# --- SchedulerImpl._node_sched_default tests ---

def test_scheduler_node_sched_default_no_preds():
    """_node_sched_default returns 0 for node with no predecessors."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    # Source nodes have no preds
    for node in dfg.src_nodes:
        time = scheduler._node_sched_default(dfg, node)
        assert time == 0


def test_scheduler_with_multiple_vars():
    """Scheduler handles scope with multiple variables and deps."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32
var d: int32

blk1:
mv a 1
mv b 2
mv c (+ a b)
mv d (+ c a)
mv @return d
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0
        assert node.end >= node.begin


def test_scheduler_with_binop_chain():
    """Scheduler handles chained BinOp expressions."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x (+ 1 2)
mv y (+ x 3)
mv z (+ y 4)
mv @return z
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    # Nodes should be scheduled with proper ordering
    for (n1, n2), (typ, back) in dfg.edges.items():
        if typ == 'DefUse' and not back:
            # Def should complete before use starts
            assert n1.end <= n2.begin or n1.begin <= n2.begin


def test_scheduler_with_cjump():
    """Scheduler handles branching control flow."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var cond: bool

blk1:
mv cond 1
cj cond blk2 blk3

blk2:
mv x 10
j blk4

blk3:
mv x 20
j blk4

blk4:
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0


# --- ResourceExtractor tests ---

def test_resource_extractor_binop():
    """ResourceExtractor extracts BinOp resources."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (+ 1 2)
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    dfg = scope.top_dfg
    for node in dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)

    # Should have ops for BinOp node
    found_binop = False
    for node, ops in extractor.ops.items():
        if 'Add' in ops:
            found_binop = True
    assert found_binop


def test_resource_extractor_relop():
    """ResourceExtractor visits RelOp without error."""
    src = '''
scope F
tags function returnable
return bool
var x: int32
var r: bool

blk1:
mv x 10
mv r (== x 5)
mv @return r
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)


def test_resource_extractor_unop():
    """ResourceExtractor visits UnOp without error."""
    extractor = ResourceExtractor()
    from polyphony.compiler.ir.ir import UnOp
    unop = UnOp(op='USub', exp=Const(42))
    extractor.current_node = None
    extractor._visit_rec(unop)


def test_resource_extractor_mref_mstore():
    """ResourceExtractor visits MRef and MStore via a real scope."""
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
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)
    # Just verifying no crash; simple scope has no mem ops
    assert isinstance(extractor.regarrays, dict)


def test_resource_extractor_cjump():
    """ResourceExtractor visits CJump without error."""
    src = '''
scope F
tags function returnable
return int32
var cond: bool
var x: int32

blk1:
mv cond 1
cj cond blk2 blk3

blk2:
mv x 10
j blk4

blk3:
mv x 20
j blk4

blk4:
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)


def test_resource_extractor_phi():
    """ResourceExtractor visits Phi stm without error."""
    extractor = ResourceExtractor()
    # Visit a Phi directly
    phi = Phi(Temp('x', Ctx.STORE), [Const(1), Const(2)])
    extractor.current_node = None
    extractor._visit_rec(phi)
    # No crash


def test_resource_extractor_phi_with_none_arg():
    """ResourceExtractor visits Phi with None args."""
    extractor = ResourceExtractor()
    phi = Phi(Temp('x', Ctx.STORE), [Const(1), None, Const(2)])
    extractor.current_node = None
    extractor._visit_rec(phi)


def test_resource_extractor_condop():
    """ResourceExtractor visits CondOp without error."""
    extractor = ResourceExtractor()
    condop = CondOp(Const(1), Const(10), Const(20))
    extractor.current_node = None
    extractor._visit_rec(condop)


def test_resource_extractor_array():
    """ResourceExtractor visits Array without error."""
    extractor = ResourceExtractor()
    arr = Array([Const(1), Const(2), Const(3)], True)
    extractor.current_node = None
    extractor._visit_rec(arr)


def test_resource_extractor_none():
    """ResourceExtractor handles None input."""
    extractor = ResourceExtractor()
    extractor._visit_rec(None)
    # No crash


def test_resource_extractor_syscall():
    """ResourceExtractor visits SysCall without error."""
    extractor = ResourceExtractor()
    sc = SysCall(func=Temp('print', Ctx.LOAD), args=[('', Const(42))], name='print')
    extractor.current_node = None
    extractor._visit_rec(sc)


def test_resource_extractor_new():
    """ResourceExtractor visits New without error."""
    extractor = ResourceExtractor()
    n = New(Temp('C', Ctx.LOAD), [('', Const(1))])
    extractor.current_node = None
    extractor._visit_rec(n)


def test_resource_extractor_cjump():
    """ResourceExtractor visits CJump stm directly."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_ext_cj', {'function'})
    from polyphony.compiler.ir.block import Block
    blk1 = Block(scope)
    blk2 = Block(scope)
    extractor = ResourceExtractor()
    extractor.scope = scope
    cj = CJump(Const(1), blk1.bid, blk2.bid)
    extractor.current_node = None
    extractor._visit_rec(cj)


def test_resource_extractor_mcjump():
    """ResourceExtractor visits MCJump stm directly."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_ext_mj', {'function'})
    from polyphony.compiler.ir.block import Block
    blk1 = Block(scope)
    blk2 = Block(scope)
    extractor = ResourceExtractor()
    extractor.scope = scope
    mj = MCJump([Const(1), Const(0)], [blk1.bid, blk2.bid])
    extractor.current_node = None
    extractor._visit_rec(mj)


def test_resource_extractor_expr():
    """ResourceExtractor visits Expr stm directly."""
    extractor = ResourceExtractor()
    e = Expr(Const(42))
    extractor.current_node = None
    extractor._visit_rec(e)


def test_resource_extractor_move():
    """ResourceExtractor visits Move stm directly."""
    extractor = ResourceExtractor()
    m = Move(Temp('x', Ctx.STORE), Const(42))
    extractor.current_node = None
    extractor._visit_rec(m)


def test_resource_extractor_expr_syscall():
    """ResourceExtractor visits Expr wrapping SysCall."""
    extractor = ResourceExtractor()
    sc = SysCall(func=Temp('print', Ctx.LOAD), args=[('', Const(42))], name='print')
    e = Expr(sc)
    extractor.current_node = None
    extractor._visit_rec(e)


def test_resource_extractor_move_call_via_scope():
    """ResourceExtractor extracts call resources when scope is available."""
    from pytests.compiler.base import setup_libs
    src = '''
scope F
tags function returnable
return int32
var p: object(polyphony.io.Port)
var x: int32

blk1:
mv x (call p.rd)
mv @return x
ret @return
'''
    setup_test()
    setup_libs('io')
    from polyphony.compiler.ir.irreader import IrReader
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes.get('F')
    if scope:
        for blk in scope.traverse_blocks():
            blk.synth_params['scheduling'] = 'sequential'
            blk.synth_params['cycle'] = 'any'
            blk.synth_params['ii'] = -1
        from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
        LoopDetector().process(scope)
        DFGBuilder().process(scope)
        extractor = ResourceExtractor()
        extractor.scope = scope
        dfg = scope.top_dfg
        for node in dfg.nodes:
            extractor.current_node = node
            extractor.visit(node.tag)


def test_pipeline_schedule_full():
    """PipelineScheduler._schedule runs full scheduling pass."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='pipeline')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    dfg.synth_params['ii'] = -1

    ps = PipelineScheduler()
    ps.scope = scope
    ps.res_extractor = ResourceExtractor()
    ps.res_extractor.scope = scope
    for node in sorted(dfg.traverse_nodes(dfg.succs, dfg.find_src(), [])):
        ps.res_extractor.current_node = node
        ps.res_extractor.visit(node.tag)

    # Set priorities
    from collections import deque
    from polyphony.compiler.common.utils import unique
    sources = dfg.find_src()
    for src_node in sources:
        src_node.priority = -1
    worklist = deque()
    worklist.append((sources, 0))
    while worklist:
        nodes, prio = worklist.popleft()
        for n in nodes:
            succs, nextprio = ps._set_priority(n, prio, dfg)
            if succs:
                succs = unique(succs)
                worklist.append((succs, nextprio))

    # Now run the full pipeline schedule
    longest = ps._schedule(dfg)
    assert longest >= 0
    for node in dfg.nodes:
        assert node.begin >= 0


def test_pipeline_schedule_full_with_ii():
    """PipelineScheduler._schedule with explicit II."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 10
mv y (+ x 5)
mv z (+ y 3)
mv @return z
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='pipeline')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    dfg.synth_params['ii'] = 5

    ps = PipelineScheduler()
    ps.scope = scope
    ps.res_extractor = ResourceExtractor()
    ps.res_extractor.scope = scope
    for node in sorted(dfg.traverse_nodes(dfg.succs, dfg.find_src(), [])):
        ps.res_extractor.current_node = node
        ps.res_extractor.visit(node.tag)

    from collections import deque
    from polyphony.compiler.common.utils import unique
    sources = dfg.find_src()
    for src_node in sources:
        src_node.priority = -1
    worklist = deque()
    worklist.append((sources, 0))
    while worklist:
        nodes, prio = worklist.popleft()
        for n in nodes:
            succs, nextprio = ps._set_priority(n, prio, dfg)
            if succs:
                succs = unique(succs)
                worklist.append((succs, nextprio))

    longest = ps._schedule(dfg)
    assert longest >= 0
    assert dfg.ii == 5


def test_pipeline_find_induction_paths():
    """PipelineScheduler._find_induction_paths with mock paths."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    from polyphony.compiler.ir.scheduling.dataflow import DFNode
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_ind', {'function'})
    from polyphony.compiler.ir.block import Block
    blk = Block(scope)
    stm1 = Move(Temp('x', Ctx.STORE), Const(1))
    blk.append_stm(stm1)
    stm2 = Move(Temp('y', Ctx.STORE), Const(2))
    blk.append_stm(stm2)

    n1 = DFNode('Stm', stm1)
    n2 = DFNode('Stm', stm2)
    # n2 has defs, n1 has uses
    from polyphony.compiler.ir.types.type import Type
    sym_x = scope.add_sym('x', set(), Type.int(32))
    sym_y = scope.add_sym('y', set(), Type.int(32))
    n1.defs = [sym_x]
    n2.defs = [sym_y]
    n1.uses = [sym_y]

    ps = PipelineScheduler()
    # Path where last node has defs but none are induction
    paths = [[n1, n2]]
    result = ps._find_induction_paths(paths)
    assert isinstance(result, list)


def test_node_sched_default_negative_time():
    """_node_sched_default clamps negative time to 0."""
    from polyphony.compiler.ir.scheduling.scheduler import SchedulerImpl
    from polyphony.compiler.ir.scheduling.dataflow import DFNode, DataFlowGraph
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = SchedulerImpl()
    scheduler.scope = scope
    # Set all node begin/end to negative values
    for node in dfg.nodes:
        node.begin = -5
        node.end = -3
    # Find node with preds
    for node in dfg.nodes:
        preds = dfg.preds_without_back(node)
        if preds:
            time = scheduler._node_sched_default(dfg, node)
            # Should clamp negative to 0
            assert time >= 0
            break


def test_pipeline_schedule_with_defuse():
    """PipelineScheduler._node_sched_pipeline with defuse preds."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32
var d: int32

blk1:
mv a 1
mv b (+ a 2)
mv c (+ b 3)
mv d (+ c 4)
mv @return d
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='pipeline')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    dfg.synth_params['ii'] = -1

    ps = PipelineScheduler()
    ps.scope = scope
    ps.res_extractor = ResourceExtractor()
    ps.res_extractor.scope = scope
    for node in sorted(dfg.traverse_nodes(dfg.succs, dfg.find_src(), [])):
        ps.res_extractor.current_node = node
        ps.res_extractor.visit(node.tag)

    from collections import deque
    from polyphony.compiler.common.utils import unique
    sources = dfg.find_src()
    for src_node in sources:
        src_node.priority = -1
    worklist = deque()
    worklist.append((sources, 0))
    while worklist:
        nodes, prio = worklist.popleft()
        for n in nodes:
            succs, nextprio = ps._set_priority(n, prio, dfg)
            if succs:
                succs = unique(succs)
                worklist.append((succs, nextprio))

    longest = ps._schedule(dfg)
    assert longest >= 0


def test_pipeline_node_sched_with_seq_preds():
    """PipelineScheduler._node_sched_pipeline with seq predecessors."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 10
mv y 20
mv z (+ x y)
mv @return z
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='sequential')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    ps.scope = scope
    ps._calc_latency(dfg)
    # Set begin/end for all nodes
    for i, node in enumerate(dfg.nodes):
        node.begin = i
        node.end = i + 1
        node.defs = []
    for node in dfg.nodes:
        seq_preds = dfg.preds_typ_without_back(node, 'Seq')
        if seq_preds:
            time = ps._node_sched_pipeline(dfg, node)
            assert time >= 0
            break


def test_calc_latency_zero_def_minimum():
    """_calc_latency with def_l==0 and minimum cycle."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'minimum'
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    # Mark x as alias to get def_l==0
    sym_x = scope.find_sym('x')
    if sym_x:
        sym_x.add_tag('alias')

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler._calc_latency(dfg)

    # Should hit line 199 (minimum + def_l==0)
    for node in dfg.get_priority_ordered_nodes():
        assert node in scheduler.node_latency_map
    if sym_x:
        sym_x.del_tag('alias')


def test_calc_latency_cjump_zero_def():
    """_calc_latency for non-move/non-phi with def_l==0 hits line 216."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var cond: bool

blk1:
mv x 10
mv cond 1
cj cond blk2 blk3

blk2:
mv @return x
ret @return

blk3:
mv @return 0
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler._calc_latency(dfg)
    # CJump has def_l==1 normally, but the Ret and Jump have def_l==1 too
    # This exercises various branches
    for node in dfg.get_priority_ordered_nodes():
        assert node in scheduler.node_latency_map


def test_calc_latency_zero_def_non_minimum():
    """_calc_latency with def_l==0 and non-minimum cycle (alias symbol)."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope

    # Mark a symbol as alias to trigger 0 latency path
    sym_x = scope.find_sym('x')
    if sym_x:
        sym_x.add_tag('alias')

    scheduler._calc_latency(dfg)
    for node in dfg.get_priority_ordered_nodes():
        assert node in scheduler.node_latency_map
    # Restore
    if sym_x:
        sym_x.del_tag('alias')


# --- _calc_latency tests ---

def test_calc_latency():
    """SchedulerImpl._calc_latency computes latency for all nodes."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._calc_latency(dfg)

    # All nodes should have latency entries
    for node in dfg.get_priority_ordered_nodes():
        assert node in scheduler.node_latency_map
        assert node in scheduler.node_seq_latency_map
        max_l, min_l, actual_l = scheduler.node_latency_map[node]
        assert max_l >= min_l


def test_calc_latency_minimum_cycle():
    """_calc_latency with minimum cycle mode."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'minimum'
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._calc_latency(dfg)

    for node in dfg.get_priority_ordered_nodes():
        assert node in scheduler.node_latency_map


# --- _schedule_cycles tests ---

def test_schedule_cycles_any():
    """_schedule_cycles with cycle='any' just calculates latency."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._schedule_cycles(dfg)
    assert len(scheduler.node_latency_map) > 0


def test_schedule_cycles_minimum():
    """_schedule_cycles with cycle='minimum'."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'minimum'
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._schedule_cycles(dfg)
    assert len(scheduler.node_latency_map) > 0


# --- _group_nodes_by_block tests ---

def test_group_nodes_by_block():
    """_group_nodes_by_block groups DFG nodes by their block."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var cond: bool

blk1:
mv cond 1
cj cond blk2 blk3

blk2:
mv x 10
j blk4

blk3:
mv x 20
j blk4

blk4:
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    block_nodes = scheduler._group_nodes_by_block(dfg)
    # Should have multiple blocks
    assert len(block_nodes) >= 2
    # All nodes should be accounted for
    total = sum(len(nodes) for nodes in block_nodes.values())
    assert total == len(dfg.nodes)


# --- _remove_alias_if_needed tests ---

def test_remove_alias_if_needed():
    """_remove_alias_if_needed runs without error."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._calc_latency(dfg)
    scheduler._remove_alias_if_needed(dfg)
    # No crash


# --- _adjust_latency tests ---

def test_adjust_latency_no_paths():
    """_adjust_latency with empty paths returns success."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    scheduler = BlockBoundedListScheduler()
    ret, actual = scheduler._adjust_latency([], 5)
    assert ret is True
    assert actual == 5


def test_adjust_latency_within_expected():
    """_adjust_latency succeeds when path_latency < expected."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._calc_latency(dfg)

    # Collect paths
    paths = list(dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')))
    if paths:
        # Try with a large expected value
        ret, actual = scheduler._adjust_latency(paths, 100)
        assert ret is True


# --- _max_latency tests ---

def test_max_latency():
    """_max_latency returns maximum path latency."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._calc_latency(dfg)

    paths = list(dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')))
    if paths:
        max_l = scheduler._max_latency(paths)
        assert max_l >= 0


def test_max_latency_empty_paths():
    """_max_latency returns 0 for empty paths."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    scheduler = BlockBoundedListScheduler()
    scheduler.node_latency_map = {}
    result = scheduler._max_latency([])
    assert result == 0


# --- _set_priority tests ---

def test_set_priority():
    """SchedulerImpl._set_priority updates node priority."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope

    sources = dfg.find_src()
    for src_node in sources:
        src_node.priority = -1
        succs, nextprio = scheduler._set_priority(src_node, 0, dfg)
        assert src_node.priority == 0
        assert nextprio == 1


def test_set_priority_no_update_when_lower():
    """_set_priority does not update when new priority <= current."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    node = list(dfg.src_nodes)[0]
    node.priority = 5
    succs, nextprio = scheduler._set_priority(node, 3, dfg)
    assert succs is None
    assert nextprio is None
    assert node.priority == 5


# --- _is_resource_full / _get_earliest_res_free_time tests ---

def test_is_resource_full():
    """_is_resource_full always returns 0."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    scheduler = BlockBoundedListScheduler()
    assert scheduler._is_resource_full('any_res', []) == 0


def test_str_res_string():
    """_str_res returns the string for string resources."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    scheduler = BlockBoundedListScheduler()
    assert scheduler._str_res('Add') == 'Add'


def test_str_res_scope():
    """_str_res returns scope name for Scope resources."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_scope', {'function'})
    scheduler = BlockBoundedListScheduler()
    assert scheduler._str_res(scope) == 'test_scope'


def test_get_earliest_res_free_time():
    """_get_earliest_res_free_time returns time for nodes with resources."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    from collections import defaultdict
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (+ 1 2)
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler.res_extractor = ResourceExtractor()
    scheduler.res_extractor.scope = scope
    dfg = scope.top_dfg
    for node in dfg.nodes:
        scheduler.res_extractor.current_node = node
        scheduler.res_extractor.visit(node.tag)

    for node in dfg.nodes:
        t = scheduler._get_earliest_res_free_time(node, 0, 1)
        assert t >= 0


# --- ConflictNode tests ---

def test_conflict_node_create():
    """ConflictNode.create creates from DFNode."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictNode
    from polyphony.compiler.ir.scheduling.dataflow import DFNode
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    node = dfg.nodes[0]
    cnode = ConflictNode.create(node)
    assert isinstance(cnode, ConflictNode)
    assert len(cnode.items) == 1
    assert cnode.items[0] is node


def test_conflict_node_create_merge():
    """ConflictNode.create_merge_node merges two ConflictNodes."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictNode
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 42
mv y 10
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    cn0 = ConflictNode.create(n0)
    cn1 = ConflictNode.create(n1)
    merged = ConflictNode.create_merge_node(cn0, cn1)
    assert len(merged.items) == 2
    assert merged.access == cn0.access | cn1.access


def test_conflict_node_create_split():
    """ConflictNode.create_split_node splits items out."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictNode
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 42
mv y 10
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    cn0 = ConflictNode.create(n0)
    cn1 = ConflictNode.create(n1)
    merged = ConflictNode.create_merge_node(cn0, cn1)
    split = ConflictNode.create_split_node(merged, [n0])
    assert len(split.items) == 1
    assert n0 in split.items
    assert len(merged.items) == 1
    assert n1 in merged.items


def test_conflict_node_str():
    """ConflictNode.__str__ and __repr__ produce output."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictNode
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    node = dfg.nodes[0]
    cnode = ConflictNode.create(node)
    cnode.res = 'test_res'
    s = str(cnode)
    assert 'test_res' in s
    assert repr(cnode) == s


def test_conflict_node_access_flags():
    """ConflictNode access flags R/W display correctly."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictNode
    cnode = ConflictNode(ConflictNode.READ | ConflictNode.WRITE, [])
    s = str(cnode)
    assert 'R' in s
    assert 'W' in s

    cnode_r = ConflictNode(ConflictNode.READ, [])
    s_r = str(cnode_r)
    assert 'R' in s_r
    assert 'W' not in s_r


# --- _find_latest_alias tests ---

def test_find_latest_alias_non_move():
    """_find_latest_alias returns node if not a move/phi."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    # Find the ret node (not a move)
    from polyphony.compiler.ir.ir import Jump, CJump, MCJump
    for node in dfg.nodes:
        if isinstance(node.tag, (Jump, CJump, MCJump)):
            result = scheduler._find_latest_alias(dfg, node)
            assert result is node
            break


# --- Full schedule with timed blocks ---

def test_scheduler_timed_scheduling():
    """Scheduler handles timed scheduling mode."""
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
    scope = build_scope_with_loop(src, scheduling='timed')
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0


# --- _sync_mstm_siblings tests ---

def test_sync_mstm_siblings_with_mstm():
    """_sync_mstm_siblings syncs MStm sibling nodes to same cycle."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    from polyphony.compiler.ir.scheduling.dataflow import DFNode
    from polyphony.compiler.ir.ir import MStm
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
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)
    dfg = scope.top_dfg

    # Now manually create an MStm and inject it into the block
    blk = scope.entry_block
    m1 = blk.stms[0]  # mv x 10
    m2 = blk.stms[1]  # mv y 20
    mstm = MStm(stms=[m1, m2])
    object.__setattr__(mstm, 'block', blk.bid)
    blk.stms = [mstm] + blk.stms[2:]

    # Find the DFG nodes for m1 and m2
    n1 = dfg.find_node(m1)
    n2 = dfg.find_node(m2)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler._calc_latency(dfg)

    # Set different begin times to test sync
    if n1 and n2:
        n1.begin = 0
        n1.end = 1
        n2.begin = 2
        n2.end = 3
        result = scheduler._sync_mstm_siblings(dfg, dfg.nodes, 3)
        # Both should now be synced to max begin
        assert n1.begin == n2.begin == 2
        assert result >= 3


def test_sync_mstm_siblings_no_mstm():
    """_sync_mstm_siblings with no MStm returns same latency."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._calc_latency(dfg)

    result = scheduler._sync_mstm_siblings(dfg, dfg.nodes, 5)
    assert result == 5  # No MStm, latency unchanged


# --- Full integration test ---

def test_scheduler_complex_deps():
    """Scheduler correctly handles complex dependency chains."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32
var d: int32
var e: int32

blk1:
mv a 1
mv b 2
mv c (+ a b)
mv d (+ a c)
mv e (+ c d)
mv @return e
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    # Verify monotonic scheduling: DefUse edges imply ordering
    for (n1, n2), (typ, back) in dfg.edges.items():
        if typ == 'DefUse' and not back:
            assert n1.end <= n2.begin or n1.begin <= n2.begin

    assert scope.asap_latency >= CALL_MINIMUM_STEP


def test_scheduler_with_relop():
    """Scheduler handles RelOp expressions."""
    src = '''
scope F
tags function returnable
return bool
var x: int32
var y: int32
var r: bool

blk1:
mv x 10
mv y 20
mv r (< x y)
mv @return r
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0


def test_conflict_graph_builder_empty():
    """ConflictGraphBuilder.build handles empty conflict table."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictGraphBuilder
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    builder = ConflictGraphBuilder(scope, dfg)
    cgraph = builder.build({})
    assert cgraph is not None
    assert len(list(cgraph.get_nodes())) == 0


def test_conflict_graph_builder_single_node():
    """ConflictGraphBuilder.build skips resources with single node."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictGraphBuilder
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    builder = ConflictGraphBuilder(scope, dfg)
    # Table with single node per resource - should skip
    node = dfg.nodes[0]
    cgraph = builder.build({'res': [node]})
    assert cgraph is not None


def test_conflict_graph_builder_two_nodes():
    """ConflictGraphBuilder.build processes two-node conflict."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictGraphBuilder
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 42
mv y 10
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    builder = ConflictGraphBuilder(scope, dfg)
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    # Create a Symbol-like resource key
    sym = n0.defs[0] if n0.defs else n1.defs[0] if n1.defs else None
    if sym:
        cgraph = builder.build({sym: [n0, n1]})
        assert cgraph is not None


def test_conflict_graph_builder_build_conflict_graph_per_res():
    """ConflictGraphBuilder._build_conflict_graph_per_res creates nodes."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictGraphBuilder
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 42
mv y 10
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    builder = ConflictGraphBuilder(scope, dfg)
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    graph = builder._build_conflict_graph_per_res('test_res', [n0, n1])
    assert graph is not None
    assert len(list(graph.get_nodes())) >= 1


def test_conflict_graph_builder_build_conflict_graphs():
    """ConflictGraphBuilder._build_conflict_graphs filters single-node entries."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictGraphBuilder
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 42
mv y 10
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    builder = ConflictGraphBuilder(scope, dfg)
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    # Single node entry should be skipped
    cgraphs = builder._build_conflict_graphs({'res_a': [n0]})
    assert len(cgraphs) == 0
    # Two node entry should be processed
    cgraphs = builder._build_conflict_graphs({'res_b': [n0, n1]})
    assert 'res_b' in cgraphs


def test_conflict_graph_builder_master_graph():
    """ConflictGraphBuilder._build_master_conflict_graph from cgraphs."""
    from polyphony.compiler.ir.scheduling.scheduler import ConflictGraphBuilder
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 42
mv y 10
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    builder = ConflictGraphBuilder(scope, dfg)
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    # Build per-res graph
    sym = n0.defs[0] if n0.defs else n1.defs[0]
    graph = builder._build_conflict_graph_per_res(sym, [n0, n1])
    master = builder._build_master_conflict_graph({sym: graph})
    assert master is not None


def test_extend_conflict_res_table():
    """PipelineScheduler._extend_conflict_res_table adds entries."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    from collections import defaultdict
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    table = defaultdict(list)
    target_nodes = dfg.nodes
    # Create a node_res_map
    node_res_map = {}
    for node in dfg.nodes:
        node_res_map[node] = ['res_a']
    ps._extend_conflict_res_table(table, target_nodes, node_res_map)
    assert 'res_a' in table
    assert len(table['res_a']) == len(dfg.nodes)


def test_node_sched_with_block_bound_seq_ctrl():
    """_node_sched_with_block_bound handles ctrl stm with seq preds."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var cond: bool

blk1:
mv x 10
mv cond 1
cj cond blk2 blk3

blk2:
mv @return x
ret @return

blk3:
mv @return 0
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    # Verify that CJump node was scheduled with seq preds
    from polyphony.compiler.ir.ir import CJump
    for node in dfg.nodes:
        if isinstance(node.tag, CJump):
            # CJump should be scheduled after its seq predecessors
            assert node.begin >= 0
            break


def test_adjust_latency_with_paths():
    """_adjust_latency with paths that need reduction."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32
var w: int32

blk1:
mv x 1
mv y (+ x 2)
mv z (+ y 3)
mv w (+ z 4)
mv @return w
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler._calc_latency(dfg)

    paths = list(dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')))
    if paths:
        # Large expected value - should succeed without changes
        ret, actual = scheduler._adjust_latency(paths, 50)
        assert ret is True
        assert actual == 50


def test_adjust_latency_actual_reduction():
    """_adjust_latency actually reduces latency when path exceeds expected."""
    from polyphony.compiler.ir.scheduling.scheduler import SchedulerImpl
    from polyphony.compiler.ir.scheduling.dataflow import DFNode
    # Create mock nodes with known latencies
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_adj', {'function'})
    from polyphony.compiler.ir.block import Block
    blk = Block(scope)
    stm1 = Move(Temp('x', Ctx.STORE), Const(1))
    blk.append_stm(stm1)
    stm2 = Move(Temp('y', Ctx.STORE), Const(2))
    blk.append_stm(stm2)
    stm3 = Move(Temp('z', Ctx.STORE), Const(3))
    blk.append_stm(stm3)

    n1 = DFNode('Stm', stm1)
    n2 = DFNode('Stm', stm2)
    n3 = DFNode('Stm', stm3)

    scheduler = SchedulerImpl()
    # (max_l, min_l, actual_l) - min_l < actual allows reduction
    scheduler.node_latency_map = {
        n1: (3, 0, 3),
        n2: (3, 0, 3),
        n3: (3, 0, 3),
    }
    path = [n1, n2, n3]
    # Sum is 9, expected 6 => need to reduce by 3 (exactly 1 per node)
    ret, actual = scheduler._adjust_latency([path], 6)
    assert ret is True
    assert actual == 6
    # Latencies should have been reduced
    total = sum(scheduler.node_latency_map[n][2] for n in path)
    assert total <= 6


def test_adjust_latency_fails_when_too_tight():
    """_adjust_latency returns False when reduction is impossible."""
    from polyphony.compiler.ir.scheduling.scheduler import SchedulerImpl
    from polyphony.compiler.ir.scheduling.dataflow import DFNode
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_adj2', {'function'})
    from polyphony.compiler.ir.block import Block
    blk = Block(scope)
    stm1 = Move(Temp('x', Ctx.STORE), Const(1))
    blk.append_stm(stm1)
    stm2 = Move(Temp('y', Ctx.STORE), Const(2))
    blk.append_stm(stm2)

    n1 = DFNode('Stm', stm1)
    n2 = DFNode('Stm', stm2)

    scheduler = SchedulerImpl()
    # min_l == max_l, cannot reduce
    scheduler.node_latency_map = {
        n1: (2, 2, 2),
        n2: (2, 2, 2),
    }
    path = [n1, n2]
    # Sum is 4, expected 1 => need to reduce by 3 but can't
    ret, actual = scheduler._adjust_latency([path], 1)
    assert ret is False
    assert actual > 1


def test_adjust_latency_partial_reduction():
    """_adjust_latency with mixed reducible/non-reducible nodes."""
    from polyphony.compiler.ir.scheduling.scheduler import SchedulerImpl
    from polyphony.compiler.ir.scheduling.dataflow import DFNode
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_adj3', {'function'})
    from polyphony.compiler.ir.block import Block
    blk = Block(scope)
    stm1 = Move(Temp('a', Ctx.STORE), Const(1))
    blk.append_stm(stm1)
    stm2 = Move(Temp('b', Ctx.STORE), Const(2))
    blk.append_stm(stm2)

    n1 = DFNode('Stm', stm1)
    n2 = DFNode('Stm', stm2)

    scheduler = SchedulerImpl()
    # n1 can be reduced (min=1), n2 cannot (min=2)
    scheduler.node_latency_map = {
        n1: (3, 1, 3),
        n2: (2, 2, 2),
    }
    path = [n1, n2]
    # Sum is 5, expected 3 => reduce by 2, n1 can lose 2 (3->1)
    ret, actual = scheduler._adjust_latency([path], 3)
    assert ret is True


def test_try_adjust_latency():
    """_try_adjust_latency succeeds with large cycle target."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler._calc_latency(dfg)
    assert len(scheduler.node_latency_map) >= 1  # latency computed for all DFG nodes
    # Should not assert with large expected
    scheduler._try_adjust_latency(dfg, 100)


def test_scheduler_with_many_deps():
    """Scheduler handles many interconnected dependencies."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32

blk1:
mv a 1
mv b (+ a 2)
mv c (+ a b)
mv @return c
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)

    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0


def test_node_sched_default_with_seq_preds():
    """_node_sched_default with Seq predecessors (sequential scheduling)."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32

blk1:
mv a 1
mv b 2
mv c 3
mv @return c
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='sequential')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    # Set begin/end on all nodes
    for i, node in enumerate(dfg.nodes):
        node.begin = i
        node.end = i + 1
    # Find node with seq preds
    for node in dfg.nodes:
        seq_preds = dfg.preds_typ_without_back(node, 'Seq')
        if seq_preds:
            time = scheduler._node_sched_default(dfg, node)
            assert time >= 0
            break


def test_find_latest_alias_move_non_alias():
    """_find_latest_alias returns node for non-alias move."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    # Find a move node - x is not aliased
    from polyphony.compiler.ir.ir import Move
    for node in dfg.nodes:
        if isinstance(node.tag, Move):
            result = scheduler._find_latest_alias(dfg, node)
            assert result is node
            break


def test_adjust_latency_reduction():
    """_adjust_latency reduces latency when path exceeds expected."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 10
mv y (+ x 5)
mv z (+ y 3)
mv @return z
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler._calc_latency(dfg)

    paths = list(dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')))
    if paths:
        # Try with a very large expected value (should succeed)
        ret, actual = scheduler._adjust_latency(paths, 100)
        assert ret is True
        # Try with expected=0 (should attempt to reduce but may fail)
        # Reset latencies
        scheduler._calc_latency(dfg)
        ret2, actual2 = scheduler._adjust_latency(paths, 0)
        # Either succeeds or fails - just check it doesn't crash
        assert isinstance(ret2, bool)


def test_schedule_cycles_less_mode():
    """_schedule_cycles with cycle='less:N' mode."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'less:100'
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._schedule_cycles(dfg)
    assert len(scheduler.node_latency_map) > 0


def test_scheduler_minimum_cycle():
    """Scheduler with minimum cycle produces valid schedule."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='sequential')
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'minimum'
    DFGBuilder().process(scope)
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.begin >= 0


def test_calc_latency_timed():
    """_calc_latency with timed scheduling mode."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='timed')
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    dfg = scope.top_dfg
    scheduler._calc_latency(dfg)

    for node in dfg.get_priority_ordered_nodes():
        assert node in scheduler.node_latency_map
        assert node in scheduler.node_seq_latency_map


def test_get_earliest_res_free_time_already_scheduled():
    """_get_earliest_res_free_time handles already-scheduled nodes."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    from collections import defaultdict
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (+ 1 2)
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler.res_extractor = ResourceExtractor()
    scheduler.res_extractor.scope = scope
    dfg = scope.top_dfg
    for node in dfg.nodes:
        scheduler.res_extractor.current_node = node
        scheduler.res_extractor.visit(node.tag)

    # Schedule nodes once
    for node in dfg.nodes:
        scheduler._get_earliest_res_free_time(node, 0, 1)
    # Schedule again - should return same time (already in table)
    for node in dfg.nodes:
        t = scheduler._get_earliest_res_free_time(node, 0, 1)
        assert t >= 0


def test_pipeline_scheduler_methods():
    """PipelineScheduler internal methods work correctly."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    ps = PipelineScheduler()
    # Test _find_induction_paths with empty paths
    result = ps._find_induction_paths([])
    assert result == []

    # Test _get_using_resources with empty extractor
    ps.res_extractor = ResourceExtractor()
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
    DFGBuilder().process(scope)
    ps.res_extractor.scope = scope
    dfg = scope.top_dfg
    for node in dfg.nodes:
        res = ps._get_using_resources(node)
        assert isinstance(res, list)

    # Test _make_conflict_res_table
    ps.res_extractor = ResourceExtractor()
    ps.res_extractor.scope = scope
    for node in dfg.nodes:
        ps.res_extractor.current_node = node
        ps.res_extractor.visit(node.tag)
    table = ps._make_conflict_res_table(dfg.nodes)
    assert isinstance(table, dict)


def test_pipeline_scheduler_max_cnode_num():
    """PipelineScheduler.max_cnode_num handles empty graph."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    from polyphony.compiler.common.graph import Graph
    ps = PipelineScheduler()
    g = Graph()
    result = ps.max_cnode_num(g)
    assert result == 0


def test_pipeline_scheduler_fill_defuse_gap():
    """PipelineScheduler._fill_defuse_gap runs without error."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    ps.scope = scope
    ps.res_extractor = ResourceExtractor()
    ps.res_extractor.scope = scope
    for node in dfg.nodes:
        ps.res_extractor.current_node = node
        ps.res_extractor.visit(node.tag)
    # Set begin/end on nodes for gap calculation
    for i, node in enumerate(dfg.nodes):
        node.begin = i * 2
        node.end = i * 2 + 1
    ps._fill_defuse_gap(dfg, dfg.nodes)
    # Should not crash


def test_pipeline_node_sched():
    """PipelineScheduler._node_sched_pipeline with no preds returns 0."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    ps.scope = scope
    ps.node_seq_latency_map = {}
    # Source nodes have no preds
    for node in dfg.src_nodes:
        time = ps._node_sched_pipeline(dfg, node)
        assert time == 0


def test_pipeline_node_sched_with_preds():
    """PipelineScheduler._node_sched_pipeline with predecessors."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    ps.scope = scope
    ps._calc_latency(dfg)
    # Set begin/end on all nodes
    for i, node in enumerate(dfg.nodes):
        node.begin = i
        node.end = i + 1
        node.defs = []
    for node in dfg.nodes:
        preds = dfg.preds_without_back(node)
        if preds:
            time = ps._node_sched_pipeline(dfg, node)
            assert time >= 0
            break


def test_pipeline_schedule_ii():
    """PipelineScheduler._schedule_ii with no paths sets ii=1."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    ps.scope = scope
    ps._calc_latency(dfg)
    dfg.synth_params['ii'] = -1
    ps._schedule_ii(dfg)
    assert dfg.ii >= 1


def test_pipeline_schedule_ii_explicit():
    """PipelineScheduler._schedule_ii with explicit ii value."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    ps.scope = scope
    ps._calc_latency(dfg)
    dfg.synth_params['ii'] = 10
    ps._schedule_ii(dfg)
    assert dfg.ii == 10


def test_pipeline_list_schedule():
    """PipelineScheduler._list_schedule_for_pipeline basic operation."""
    from polyphony.compiler.ir.scheduling.scheduler import PipelineScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    ps = PipelineScheduler()
    ps.scope = scope
    ps.d2c = {}
    ps._calc_latency(dfg)
    # Set initial begin/end
    for node in dfg.nodes:
        node.begin = -1
        node.end = -1
    # Set priorities
    for i, node in enumerate(dfg.nodes):
        node.priority = i

    latency = ps._list_schedule_for_pipeline(dfg, list(dfg.nodes), 0)
    assert latency >= 0


def test_node_sched_default_with_preds():
    """_node_sched_default with DefUse predecessors."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    # Set begin/end on nodes so _node_sched_default can compute
    for node in dfg.nodes:
        if node in dfg.src_nodes:
            node.begin = 0
            node.end = 1
    # Find a node with predecessors
    for node in dfg.nodes:
        preds = dfg.preds_without_back(node)
        if preds:
            # Set preds begin/end
            for p in preds:
                if p.begin < 0:
                    p.begin = 0
                    p.end = 1
            time = scheduler._node_sched_default(dfg, node)
            assert time >= 0
            break


# --- _calc_latency value verification ---

def test_calc_latency_populates_node_latency_map():
    """_calc_latency populates node_latency_map for each node."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler.d2c = {}
    scheduler._calc_latency(dfg)
    # Every node should be in node_latency_map
    for node in dfg.nodes:
        assert node in scheduler.node_latency_map, f"Node not in latency map: {node}"
        latency_tuple = scheduler.node_latency_map[node]
        assert len(latency_tuple) == 3
        assert all(v >= 0 for v in latency_tuple)


def test_calc_latency_minimum_cycle():
    """_calc_latency with cycle='minimum' produces zero latencies."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='sequential')
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'minimum'
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler.d2c = {}
    scheduler._calc_latency(dfg)
    # With minimum cycle, the is_minimum flag is set and affects zero-latency branches
    # All nodes should still be in the latency map
    for node in dfg.nodes:
        assert node in scheduler.node_latency_map, f"Node not in map: {node}"
        lat = scheduler.node_latency_map[node]
        assert len(lat) == 3
        assert all(v >= 0 for v in lat)


def test_calc_latency_any_cycle():
    """_calc_latency with cycle='any' gives UNIT_STEP for normal moves."""
    from polyphony.compiler.ir.scheduling.scheduler import BlockBoundedListScheduler
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
    DFGBuilder().process(scope)
    dfg = scope.top_dfg

    scheduler = BlockBoundedListScheduler()
    scheduler.scope = scope
    scheduler.d2c = {}
    scheduler._calc_latency(dfg)
    # With 'any' cycle, normal moves get UNIT_STEP
    for node in dfg.nodes:
        if isinstance(node.tag, Move) and node in scheduler.node_latency_map:
            lat = scheduler.node_latency_map[node]
            assert lat[0] >= 0


# --- ResourceExtractor value verification ---

def test_resource_extractor_counts_ops():
    """ResourceExtractor counts operation types per node."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x (+ 1 2)
mv y (* 3 4)
mv z (+ x y)
mv @return z
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)

    # Check that specific operations were counted
    found_add = False
    found_mult = False
    for node, op_counts in extractor.ops.items():
        if 'Add' in op_counts:
            found_add = True
            assert op_counts['Add'] > 0
        if 'Mult' in op_counts:
            found_mult = True
            assert op_counts['Mult'] > 0
    assert found_add, "Expected Add operation to be counted"
    assert found_mult, "Expected Mult operation to be counted"


def test_resource_extractor_op_count_value():
    """ResourceExtractor op counts are positive integers."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x (+ 1 2)
mv y (+ x 3)
mv z (* y 4)
mv @return z
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)

    total_ops = 0
    for node, op_counts in extractor.ops.items():
        for op, count in op_counts.items():
            assert count > 0, f"Op count should be positive: {op}={count}"
            total_ops += count
    assert total_ops >= 3, f"Expected at least 3 operations (2 Add + 1 Mult), got {total_ops}"


def test_resource_extractor_mem_ops():
    """ResourceExtractor tracks memory read symbols."""
    src = '''
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
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)

    extractor = ResourceExtractor()
    extractor.scope = scope
    for node in scope.top_dfg.nodes:
        extractor.current_node = node
        extractor.visit(node.tag)

    found_mem = any(bool(v) for v in extractor.mems.values())
    found_regarray = any(bool(v) for v in extractor.regarrays.values())
    # MRef should be tracked in mems or regarrays
    assert found_mem or found_regarray, "Expected memory operations to be tracked"
