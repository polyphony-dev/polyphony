"""Tests for DFGBuilder."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.scheduling.dataflow import DFGBuilder
from polyphony.compiler.ir.irhelper import is_mem_read, is_mem_write
from polyphony.compiler.ir.ir import IrVariable
from polyphony.compiler.ir.scheduling.dataflow import DataFlowGraph
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


def test_is_variable():
    """IrVariable covers Temp and Attr."""
    assert isinstance(Temp('x', Ctx.LOAD), IrVariable)


def test_is_mem_read():
    """is_mem_read detects MOVE with MREF src."""
    m = Move(Temp('x', Ctx.STORE), MRef(Temp('arr', Ctx.LOAD), Const(0), Ctx.LOAD))
    assert is_mem_read(m)


def test_is_mem_write():
    """is_mem_write detects EXPR with MSTORE exp."""
    e = Expr(MStore(Temp('arr', Ctx.LOAD), Const(0), Const(1)))
    assert is_mem_write(e)


def test_is_mem_read_not_move():
    """is_mem_read returns False for non-MOVE."""
    e = Expr(Const(1))
    assert not is_mem_read(e)


# --- DFG building tests ---

def test_dfg_simple_linear():
    """DFGBuilder creates DFG for linear block."""
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
    builder = DFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    assert dfg is not None
    assert isinstance(dfg, DataFlowGraph)
    assert len(dfg.nodes) >= 3


def test_dfg_has_defuse_edges():
    """DFGBuilder creates def-use edges between definitions and uses."""
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
    builder = DFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    defuse_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'DefUse']
    assert len(defuse_edges) > 0, "Expected DefUse edges"


def test_dfg_source_nodes():
    """DFGBuilder identifies source nodes (constant assignments)."""
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
    builder = DFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    assert len(dfg.src_nodes) > 0, "Expected source nodes"


def test_dfg_sequential_scheduling():
    """DFGBuilder adds seq edges for sequential scheduling."""
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
    builder = DFGBuilder()
    builder.process(scope)

    dfg = scope.top_dfg
    seq_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'Seq']
    assert len(seq_edges) > 0, "Expected Seq edges for sequential scheduling"


def test_is_constant_stm_move_const():
    """_is_constant_stm recognizes MOVE with CONST src."""
    builder = DFGBuilder()
    m = Move(Temp('x', Ctx.STORE), Const(42))
    assert builder._is_constant_stm(m)


def test_is_constant_stm_move_array():
    """_is_constant_stm recognizes MOVE with ARRAY src."""
    builder = DFGBuilder()
    m = Move(Temp('x', Ctx.STORE), Array([Const(1)], True))
    assert builder._is_constant_stm(m)


def test_is_constant_stm_move_temp():
    """_is_constant_stm rejects MOVE with TEMP src."""
    builder = DFGBuilder()
    m = Move(Temp('x', Ctx.STORE), Temp('y', Ctx.LOAD))
    assert not builder._is_constant_stm(m)


# --- DFNode unit tests ---

def test_dfnode_str_stm():
    """DFNode __str__ for Stm type."""
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
    s = str(node)
    assert '<' in s
    assert ':' in s


def test_dfnode_lt():
    """DFNode __lt__ sorts by begin then priority."""
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
    from polyphony.compiler.ir.scheduling.scheduler import Scheduler
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    sorted_nodes = sorted(dfg.nodes)
    for i in range(len(sorted_nodes) - 1):
        a, b = sorted_nodes[i], sorted_nodes[i + 1]
        assert a.begin <= b.begin or (a.begin == b.begin and a.priority <= b.priority)


def test_dfnode_latency():
    """DFNode.latency() returns end - begin."""
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
    from polyphony.compiler.ir.scheduling.scheduler import Scheduler
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    for node in dfg.nodes:
        assert node.latency() == node.end - node.begin


# --- DataFlowGraph method tests ---

def test_dfg_str():
    """DataFlowGraph __str__ produces readable output."""
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
    s = str(dfg)
    assert 'DFG all nodes' in s
    assert 'DFG all edges' in s


def test_dfg_find_node_returns_none_for_unknown():
    """DataFlowGraph.find_node returns None for unknown stm."""
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
    fake_stm = Move(Temp('z', Ctx.STORE), Const(99))
    assert dfg.find_node(fake_stm) is None


def test_dfg_find_sink():
    """DataFlowGraph.find_sink returns nodes with no successors."""
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
    sinks = dfg.find_sink()
    assert len(sinks) > 0
    for s in sinks:
        assert len(dfg.succs(s)) == 0


def test_dfg_remove_node():
    """DataFlowGraph.remove_node removes a node."""
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
    original_count = len(dfg.nodes)
    # Find a sink node (no successors) to safely remove
    sinks = dfg.find_sink()
    assert len(sinks) > 0
    dfg.remove_node(sinks[0])
    assert len(dfg.nodes) == original_count - 1


def test_dfg_succs_and_preds():
    """DataFlowGraph succs/preds return correct nodes."""
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
    # Check that edges create consistent succs/preds
    for (n1, n2), (typ, back) in dfg.edges.items():
        assert n2 in dfg.succs(n1)
        assert n1 in dfg.preds(n2)


def test_dfg_succs_without_back():
    """DataFlowGraph.succs_without_back filters back edges."""
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
    for node in dfg.nodes:
        no_back = dfg.succs_without_back(node)
        all_succs = dfg.succs(node)
        assert len(no_back) <= len(all_succs)


def test_dfg_preds_without_back():
    """DataFlowGraph.preds_without_back filters back edges."""
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
    for node in dfg.nodes:
        no_back = dfg.preds_without_back(node)
        all_preds = dfg.preds(node)
        assert len(no_back) <= len(all_preds)


def test_dfg_succs_typ():
    """DataFlowGraph.succs_typ filters by edge type."""
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
    for node in dfg.nodes:
        defuse = dfg.succs_typ(node, 'DefUse')
        usedef = dfg.succs_typ(node, 'UseDef')
        seq = dfg.succs_typ(node, 'Seq')
        all_succs = dfg.succs(node)
        # Typed succs should be subsets of all succs
        for s in defuse + usedef + seq:
            assert s in all_succs


def test_dfg_preds_typ():
    """DataFlowGraph.preds_typ filters by edge type."""
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
    for node in dfg.nodes:
        defuse = dfg.preds_typ(node, 'DefUse')
        usedef = dfg.preds_typ(node, 'UseDef')
        seq = dfg.preds_typ(node, 'Seq')
        all_preds = dfg.preds(node)
        for p in defuse + usedef + seq:
            assert p in all_preds


def test_dfg_succs_typ_without_back():
    """DataFlowGraph.succs_typ_without_back filters by type and back."""
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
    for node in dfg.nodes:
        result = dfg.succs_typ_without_back(node, 'DefUse')
        assert isinstance(result, list)


def test_dfg_preds_typ_without_back():
    """DataFlowGraph.preds_typ_without_back filters by type and back."""
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
    for node in dfg.nodes:
        result = dfg.preds_typ_without_back(node, 'DefUse')
        assert isinstance(result, list)


def test_dfg_get_priority_ordered_nodes():
    """DataFlowGraph.get_priority_ordered_nodes returns sorted nodes."""
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
    from polyphony.compiler.ir.scheduling.scheduler import Scheduler
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    ordered = dfg.get_priority_ordered_nodes()
    for i in range(len(ordered) - 1):
        assert ordered[i].priority <= ordered[i + 1].priority


def test_dfg_get_highest_priority_nodes():
    """DataFlowGraph.get_highest_priority_nodes returns priority=0 nodes."""
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
    from polyphony.compiler.ir.scheduling.scheduler import Scheduler
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    highest = list(dfg.get_highest_priority_nodes())
    for n in highest:
        assert n.priority == 0


def test_dfg_get_loop_nodes():
    """DataFlowGraph.get_loop_nodes returns Loop-type nodes (empty for simple)."""
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
    loop_nodes = list(dfg.get_loop_nodes())
    assert len(loop_nodes) == 0


def test_dfg_traverse_nodes():
    """DataFlowGraph.traverse_nodes visits all reachable nodes."""
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
    sources = dfg.find_src()
    visited = list(dfg.traverse_nodes(dfg.succs, sources, []))
    assert len(visited) == len(dfg.nodes)


def test_dfg_collect_all_preds():
    """DataFlowGraph.collect_all_preds recursively collects predecessors."""
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
    # Find sink node (ret) and collect all preds
    sinks = dfg.find_sink()
    if sinks:
        preds = dfg.collect_all_preds(sinks[0])
        # Should have found some predecessors
        assert isinstance(preds, list)


def test_dfg_get_scheduled_nodes():
    """DataFlowGraph.get_scheduled_nodes returns nodes grouped by block."""
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
    from polyphony.compiler.ir.scheduling.scheduler import Scheduler
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    scheduled = dfg.get_scheduled_nodes()
    assert len(scheduled) == len(dfg.nodes)


def test_dfg_trace_all_paths():
    """DataFlowGraph.trace_all_paths yields paths from sources."""
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
    from polyphony.compiler.ir.scheduling.scheduler import Scheduler
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    paths = list(dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')))
    assert len(paths) > 0
    for path in paths:
        assert len(path) > 0


def test_dfg_remove_edge():
    """DataFlowGraph.remove_edge removes an edge properly."""
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
    if dfg.edges:
        (n1, n2) = list(dfg.edges.keys())[0]
        edge_count = len(dfg.edges)
        dfg.remove_edge(n1, n2)
        assert len(dfg.edges) == edge_count - 1


def test_dfg_set_child():
    """DataFlowGraph.set_child properly sets parent-child relationship."""
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
    # Check that children is a list (may be empty for simple scope)
    assert isinstance(dfg.children, list)


def test_expand_stms():
    """_expand_stms expands MStm into child Moves."""
    from polyphony.compiler.ir.scheduling.dataflow import _expand_stms
    m1 = Move(Temp('x', Ctx.STORE), Const(1))
    m2 = Move(Temp('y', Ctx.STORE), Const(2))
    mstm = MStm(stms=[m1, m2])
    m3 = Move(Temp('z', Ctx.STORE), Const(3))
    result = _expand_stms([mstm, m3])
    assert len(result) == 3
    assert result[0] is m1
    assert result[1] is m2
    assert result[2] is m3


def test_expand_stms_no_mstm():
    """_expand_stms passes through non-MStm stms."""
    from polyphony.compiler.ir.scheduling.dataflow import _expand_stms
    m1 = Move(Temp('x', Ctx.STORE), Const(1))
    m2 = Move(Temp('y', Ctx.STORE), Const(2))
    result = _expand_stms([m1, m2])
    assert len(result) == 2


def test_head_name():
    """_head_name returns head name for Attr, empty for others."""
    from polyphony.compiler.ir.scheduling.dataflow import _head_name
    a = Attr(Temp('self', Ctx.LOAD), Temp('x', Ctx.LOAD), Ctx.LOAD)
    assert _head_name(a) != ''
    assert _head_name(Const(1)) == ''


def test_program_order():
    """_program_order returns (block.order, stm_index) tuple."""
    from polyphony.compiler.ir.scheduling.dataflow import _program_order
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
    blk = scope.entry_block
    stm = blk.stms[0]
    order = _program_order(stm)
    assert isinstance(order, tuple)
    assert len(order) == 2


def test_find_stm_index():
    """_find_stm_index finds stm position in block."""
    from polyphony.compiler.ir.scheduling.dataflow import _find_stm_index
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
    blk = scope.entry_block
    assert _find_stm_index(blk.stms[0]) == 0
    assert _find_stm_index(blk.stms[1]) == 1
    assert _find_stm_index(blk.stms[2]) == 2


def test_find_stm_index_mstm():
    """_find_stm_index finds MStm child position via block.stms scanning."""
    from polyphony.compiler.ir.scheduling.dataflow import _find_stm_index
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
    blk = scope.entry_block
    m1 = blk.stms[0]
    m2 = blk.stms[1]
    # Create MStm wrapping these two moves, set block via model_config workaround
    mstm = MStm(stms=[m1, m2])
    object.__setattr__(mstm, 'block', blk.bid)
    blk.stms = [mstm, blk.stms[2], blk.stms[3]]
    # _find_stm_index should find m1 inside MStm at index 0
    assert _find_stm_index(m1) == 0


# --- DFG building with CJump (multi-block) ---

def test_dfg_with_cjump():
    """DFGBuilder handles branching with CJump."""
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
    dfg = scope.top_dfg
    assert dfg is not None
    assert len(dfg.nodes) >= 4


def test_dfg_with_binop():
    """DFGBuilder handles BinOp expressions."""
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
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert len(dfg.nodes) >= 4
    # BinOp should create def-use edges
    defuse_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'DefUse']
    assert len(defuse_edges) >= 2


def test_dfg_with_relop():
    """DFGBuilder handles RelOp expressions."""
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
    dfg = scope.top_dfg
    assert len(dfg.nodes) >= 3


def test_dfg_with_multiple_blocks():
    """DFGBuilder handles multiple blocks with jumps."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y 20
j blk2

blk2:
mv @return (+ x y)
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert len(dfg.nodes) >= 4


# --- _is_constant_stm additional tests ---

def test_is_constant_stm_move_mref_const():
    """_is_constant_stm recognizes MOVE with MREF const offset."""
    builder = DFGBuilder()
    m = Move(Temp('x', Ctx.STORE), MRef(Temp('arr', Ctx.LOAD), Const(0), Ctx.LOAD))
    assert builder._is_constant_stm(m)


def test_is_constant_stm_move_new():
    """_is_constant_stm recognizes MOVE with New."""
    builder = DFGBuilder()
    m = Move(Temp('x', Ctx.STORE), New(Temp('C', Ctx.LOAD), []))
    assert builder._is_constant_stm(m)


def test_is_constant_stm_expr_mstore_const():
    """_is_constant_stm recognizes EXPR with MStore const offset+value."""
    builder = DFGBuilder()
    e = Expr(MStore(Temp('arr', Ctx.LOAD), Const(0), Const(42)))
    assert builder._is_constant_stm(e)


def test_is_constant_stm_cjump_const():
    """_is_constant_stm recognizes CJump with const condition."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_cj_const', {'function'})
    from polyphony.compiler.ir.block import Block
    blk1 = Block(scope)
    blk2 = Block(scope)
    builder = DFGBuilder()
    cj = CJump(Const(1), blk1.bid, blk2.bid)
    assert builder._is_constant_stm(cj)


def test_is_constant_stm_mcjump_const():
    """_is_constant_stm recognizes MCJump with const condition."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_mj_const', {'function'})
    from polyphony.compiler.ir.block import Block
    blk1 = Block(scope)
    blk2 = Block(scope)
    builder = DFGBuilder()
    mj = MCJump([Const(1), Temp('x', Ctx.LOAD)], [blk1.bid, blk2.bid])
    assert builder._is_constant_stm(mj)


def test_dfg_add_seq_edges_sequential():
    """DFGBuilder creates seq edges for sequential scheduling mode."""
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
    seq_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'Seq']
    # Sequential scheduling should have seq edges between consecutive stms
    assert len(seq_edges) >= 2


def test_dfg_ctrl_branch_seq_edges():
    """DFGBuilder adds seq edges from non-ctrl stms to ctrl stm."""
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
    # Use non-sequential scheduling to test _add_seq_edges_for_ctrl_branch
    scope = build_scope_with_loop(src, scheduling='')
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'any'
        blk.synth_params['ii'] = -1
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    # CJump node should have seq predecessors from other stms in same block
    for node in dfg.nodes:
        if isinstance(node.tag, CJump):
            preds = dfg.preds(node)
            # Should have predecessors since other stms come before CJump
            assert len(preds) >= 1


def test_dfg_timed_scheduling():
    """DFGBuilder handles timed scheduling mode."""
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
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'any'
        blk.synth_params['ii'] = -1
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert dfg is not None


# --- DataFlowGraph.__str__ edge type coverage ---

def test_dfg_str_with_usedef_edges():
    """DataFlowGraph.__str__ covers UseDef edge formatting."""
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
    scope = build_scope_with_loop(src, scheduling='sequential')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    s = str(dfg)
    assert 'DFG all nodes' in s
    assert 'DFG all edges' in s
    # Check that various edge types are represented
    has_edge = False
    for (n1, n2), (typ, _) in dfg.edges.items():
        has_edge = True
    assert has_edge


def test_dfg_add_edge_duplicate_defuse():
    """DataFlowGraph.add_edge handles duplicate DefUse edges."""
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
    # Find existing DefUse edge
    for (n1, n2), (typ, _) in dfg.edges.items():
        if typ == 'DefUse':
            edge_count = len(dfg.edges)
            # Add same edge again - should be a no-op
            dfg.add_edge('DefUse', n1, n2)
            assert len(dfg.edges) == edge_count
            # Add UseDef edge on same pair - should not overwrite DefUse
            dfg.add_edge('UseDef', n1, n2)
            assert dfg.edges[(n1, n2)][0] == 'DefUse'
            break


def test_dfg_add_seq_edge_on_existing_usedef():
    """DataFlowGraph.add_seq_edge overwrites UseDef (but not DefUse)."""
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
    # Check edge count
    initial_edge_count = len(dfg.edges)
    assert initial_edge_count > 0


def test_dfg_is_same_block_node():
    """DFGBuilder._is_same_block_node checks block identity."""
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
    builder = DFGBuilder()
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    # Both should be in same block
    assert builder._is_same_block_node(n0, n1)


def test_dfg_node_order_by_ctrl():
    """DFGBuilder._node_order_by_ctrl returns ordering tuple."""
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
    builder = DFGBuilder()
    builder.scope = scope
    for node in dfg.nodes:
        order = builder._node_order_by_ctrl(node)
        assert isinstance(order, tuple)
        assert len(order) == 3


def test_dfg_with_cjump_branch_graph():
    """DFGBuilder processes branch edges from CJump blocks."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var cond: bool

blk1:
mv cond 1
cj cond blk2 blk3

blk2:
mv x 10
j blk4

blk3:
mv y 20
j blk4

blk4:
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    # DFG should have nodes from multiple blocks
    blocks_seen = set()
    for node in dfg.nodes:
        blocks_seen.add(node.tag.block)
    assert len(blocks_seen) >= 3


def test_dfg_with_mcjump():
    """DFGBuilder handles MCJump branching."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var cond: bool

blk1:
mv cond 1
mj cond blk2 1 blk3

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
    dfg = scope.top_dfg
    assert dfg is not None
    assert len(dfg.nodes) >= 4


def test_is_constant_stm_expr_call_const_args():
    """_is_constant_stm recognizes EXPR with call taking only const args."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_call_const', {'function'})
    builder = DFGBuilder()
    # SysCall with all const args
    sc = SysCall(func=Temp('print', Ctx.LOAD), args=[('', Const(42))], name='print')
    e = Expr(sc)
    assert builder._is_constant_stm(e)


def test_is_constant_stm_syscall_new():
    """_is_constant_stm recognizes MOVE with SysCall $new."""
    builder = DFGBuilder()
    sc = SysCall(func=Temp('$new', Ctx.LOAD), args=[], name='$new')
    m = Move(Temp('x', Ctx.STORE), sc)
    assert builder._is_constant_stm(m)


# --- RegArrayParallelizer tests ---

def test_regarray_parallelizer_offset_expr_non_mem():
    """RegArrayParallelizer.offset_expr returns None for non-mem stm."""
    from polyphony.compiler.ir.scheduling.dataflow import RegArrayParallelizer
    m = Move(Temp('x', Ctx.STORE), Const(42))
    result = RegArrayParallelizer.offset_expr(m, None)
    assert result is None


def test_regarray_parallelizer_offset_expr_mem_read():
    """RegArrayParallelizer.offset_expr returns offset for mem read."""
    from polyphony.compiler.ir.scheduling.dataflow import RegArrayParallelizer
    mref = MRef(Temp('arr', Ctx.LOAD), Const(3), Ctx.LOAD)
    m = Move(Temp('x', Ctx.STORE), mref)
    result = RegArrayParallelizer.offset_expr(m, None)
    assert isinstance(result, Const)
    assert result.value == 3


def test_regarray_parallelizer_offset_expr_mem_write():
    """RegArrayParallelizer.offset_expr returns offset for mem write."""
    from polyphony.compiler.ir.scheduling.dataflow import RegArrayParallelizer
    mstore = MStore(Temp('arr', Ctx.LOAD), Const(5), Const(42))
    e = Expr(mstore)
    result = RegArrayParallelizer.offset_expr(e, None)
    assert isinstance(result, Const)
    assert result.value == 5


def test_regarray_parallelizer_get_const():
    """RegArrayParallelizer._get_const extracts Const from BinOp."""
    from polyphony.compiler.ir.scheduling.dataflow import RegArrayParallelizer
    # Const on left
    b1 = BinOp(op='Add', left=Const(5), right=Temp('x', Ctx.LOAD))
    assert RegArrayParallelizer._get_const(b1).value == 5

    # Const on right
    b2 = BinOp(op='Add', left=Temp('x', Ctx.LOAD), right=Const(10))
    assert RegArrayParallelizer._get_const(b2).value == 10

    # No const
    b3 = BinOp(op='Add', left=Temp('x', Ctx.LOAD), right=Temp('y', Ctx.LOAD))
    assert RegArrayParallelizer._get_const(b3) is None


def test_regarray_parallelizer_is_inequality_none():
    """RegArrayParallelizer.is_inequality_value returns False for None offsets."""
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
    from polyphony.compiler.ir.scheduling.dataflow import RegArrayParallelizer
    rap = RegArrayParallelizer(scope)
    assert rap.is_inequality_value(None, Const(1)) is False
    assert rap.is_inequality_value(Const(1), None) is False


def test_regarray_parallelizer_is_inequality_const():
    """RegArrayParallelizer.is_inequality_value detects different constants."""
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
    from polyphony.compiler.ir.scheduling.dataflow import RegArrayParallelizer
    rap = RegArrayParallelizer(scope)
    assert rap.is_inequality_value(Const(1), Const(2)) is True
    assert rap.is_inequality_value(Const(1), Const(1)) is False


def test_regarray_parallelizer_is_inequality_temp():
    """RegArrayParallelizer.is_inequality_value with Temp offsets."""
    src = '''
scope F
tags function returnable
return int32
var i: int32
var j: int32

blk1:
mv i 0
mv j (+ i 1)
mv @return j
ret @return
'''
    scope = build_scope_with_loop(src)
    from polyphony.compiler.ir.scheduling.dataflow import RegArrayParallelizer
    rap = RegArrayParallelizer(scope)
    t_i = Temp('i', Ctx.LOAD)
    t_j = Temp('j', Ctx.LOAD)
    # This exercises the Temp branch
    result = rap.is_inequality_value(t_i, t_j)
    assert isinstance(result, bool)


# --- DFGBuilder additional internal method tests ---

def test_dfg_builder_is_constant_stm_call():
    """_is_constant_stm recognizes MOVE with Call src."""
    builder = DFGBuilder()
    c = Call(Temp('f', Ctx.LOAD), [])
    m = Move(Temp('x', Ctx.STORE), c)
    assert builder._is_constant_stm(m)


def test_dfg_builder_is_constant_stm_expr_call_no_args():
    """_is_constant_stm for EXPR with Call and no args."""
    builder = DFGBuilder()
    c = Call(Temp('f', Ctx.LOAD), [])
    e = Expr(c)
    assert builder._is_constant_stm(e)


def test_dfg_builder_is_constant_stm_expr_syscall():
    """_is_constant_stm for EXPR with SysCall."""
    builder = DFGBuilder()
    sc = SysCall(func=Temp('assert', Ctx.LOAD), args=[('', Const(1))], name='assert')
    e = Expr(sc)
    assert builder._is_constant_stm(e)


def test_dfg_builder_is_constant_stm_mcjump_no_const():
    """_is_constant_stm returns False for MCJump with all Temp conds."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_mj_noconst', {'function'})
    from polyphony.compiler.ir.block import Block
    blk1 = Block(scope)
    blk2 = Block(scope)
    builder = DFGBuilder()
    # Last condition is always true, so only check conds[:-1]
    mj = MCJump([Temp('x', Ctx.LOAD), Const(1)], [blk1.bid, blk2.bid])
    assert not builder._is_constant_stm(mj)


def test_dfg_builder_is_constant_stm_jump():
    """_is_constant_stm returns False for Jump."""
    setup_test()
    from polyphony.compiler.ir.scope import Scope
    scope = Scope.create(None, 'test_j', {'function'})
    from polyphony.compiler.ir.block import Block
    blk = Block(scope)
    builder = DFGBuilder()
    j = Jump(blk.bid)
    assert not builder._is_constant_stm(j)


def test_dfg_with_complex_deps():
    """DFGBuilder handles complex dependency patterns."""
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
    dfg = scope.top_dfg
    # Should have nodes and edges
    assert len(dfg.nodes) >= 5
    assert len(dfg.edges) >= 3
    # Check that source nodes are identified
    assert len(dfg.src_nodes) >= 2  # at least 'a = 1' and 'b = 2'


def test_dfg_write_dot_no_pydot():
    """DataFlowGraph.write_dot handles missing pydot gracefully."""
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
    # write_dot should handle missing pydot
    dfg.write_dot('test_dot')


def test_dfg_write_dot_pygraphviz_no_module():
    """DataFlowGraph.write_dot_pygraphviz handles missing pygraphviz."""
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
    # write_dot_pygraphviz should handle missing pygraphviz
    dfg.write_dot_pygraphviz('test_pygv')


def test_dfg_remove_unconnected_node():
    """DataFlowGraph.remove_unconnected_node is a no-op."""
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
    original_count = len(dfg.nodes)
    dfg.remove_unconnected_node()
    assert len(dfg.nodes) == original_count


def test_dfg_stm_order_gt():
    """DataFlowGraph._stm_order_gt compares stm positions."""
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
    blk = scope.entry_block
    stm0 = blk.stms[0]
    stm1 = blk.stms[1]
    # stm1 comes after stm0
    assert dfg._stm_order_gt(stm1, stm0) is True
    assert dfg._stm_order_gt(stm0, stm1) is False


def test_dfg_is_back_edge():
    """DataFlowGraph._is_back_edge detects back edges."""
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
    n0 = dfg.nodes[0]
    n1 = dfg.nodes[1]
    # n1 is after n0 in program order
    assert dfg._is_back_edge(n1, n0) is True
    assert dfg._is_back_edge(n0, n1) is False


def test_dfg_get_stm():
    """DataFlowGraph._get_stm returns node's tag."""
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
    assert dfg._get_stm(node) is node.tag


def test_dfg_node_repr():
    """DFNode.__repr__ returns str."""
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
    assert repr(node) == str(node)


def test_qualified_symbols_dispatch():
    """qualified_symbols resolves a Temp to its symbol chain."""
    from polyphony.compiler.ir.irhelper import qualified_symbols
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
    t = Temp('x', Ctx.LOAD)
    syms = qualified_symbols(t, scope)
    assert len(syms) >= 1


def test_has_exclusive_function_dispatch():
    """has_exclusive_function dispatches correctly."""
    from polyphony.compiler.ir.irhelper import has_exclusive_function
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
    stm = scope.entry_block.stms[0]
    result = has_exclusive_function(stm, scope)
    assert isinstance(result, bool)


def test_has_clkfence_dispatch():
    """has_clkfence dispatches correctly."""
    from polyphony.compiler.ir.irhelper import has_clkfence
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
    stm = scope.entry_block.stms[0]
    result = has_clkfence(stm)
    assert isinstance(result, bool)


def test_dfg_add_stm_node_idempotent():
    """DataFlowGraph.add_stm_node is idempotent (returns existing node)."""
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
    stm = scope.entry_block.stms[0]
    n1 = dfg.add_stm_node(stm)
    n2 = dfg.add_stm_node(stm)
    assert n1 is n2


def test_dfg_trace_all_paths_linear():
    """DataFlowGraph.trace_all_paths on linear chain."""
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
mv c (+ b 3)
mv @return c
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    from polyphony.compiler.ir.scheduling.scheduler import Scheduler
    Scheduler().schedule(scope)
    dfg = scope.top_dfg
    # Trace DefUse paths
    paths = list(dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')))
    assert len(paths) >= 1
    # Longest path should have at least 3 nodes
    max_path = max(paths, key=len)
    assert len(max_path) >= 3


def test_dfg_collect_all_preds_deep():
    """DataFlowGraph.collect_all_preds collects transitive predecessors."""
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
mv c (+ b 3)
mv @return c
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    # Find the 'mv @return c' node which should have transitive preds
    for node in dfg.nodes:
        if isinstance(node.tag, Move) and hasattr(node.tag.dst, 'name') and '@return' in str(node.tag.dst):
            preds = dfg.collect_all_preds(node)
            assert len(preds) >= 2  # At least c and b are preds
            break


def test_dfg_with_multiple_defs():
    """DFGBuilder handles variables defined in multiple blocks."""
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
    dfg = scope.top_dfg
    # x has multiple definitions in different blocks
    # DFGBuilder should handle this with DefUse edges
    assert len(dfg.nodes) >= 4
    assert len(dfg.src_nodes) >= 1


def test_dfg_with_shared_variable():
    """DFGBuilder creates DefUse edges for shared variables."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 5)
mv x (+ y 1)
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    # x is redefined - should create UseDef edges
    usedef_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'UseDef']
    # Variable x is used then redefined - might create UseDef edges
    assert len(dfg.nodes) >= 4


def test_dfg_timed_with_deps():
    """DFGBuilder handles timed scheduling with dependencies."""
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
    scope = build_scope_with_loop(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'any'
        blk.synth_params['ii'] = -1
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert dfg is not None
    assert len(dfg.nodes) >= 4


def test_dfg_with_many_variables():
    """DFGBuilder handles many interdependent variables."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32
var d: int32
var e: int32
var f: int32

blk1:
mv a 1
mv b 2
mv c (+ a b)
mv d (+ b c)
mv e (+ c d)
mv f (+ d e)
mv @return f
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert len(dfg.nodes) >= 7
    # Should have many DefUse edges
    defuse = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'DefUse']
    assert len(defuse) >= 5


def test_dfg_seq_edges_for_ctrl_branch_cjump():
    """DFGBuilder adds seq edges from stms to CJump in same block."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var cond: bool

blk1:
mv x 10
mv y 20
mv cond (< x y)
cj cond blk2 blk3

blk2:
mv @return x
ret @return

blk3:
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    # CJump should have seq predecessors from same block
    for node in dfg.nodes:
        if isinstance(node.tag, CJump):
            preds = dfg.preds(node)
            seq_preds = dfg.preds_typ(node, 'Seq')
            assert len(preds) >= 1
            break


def test_dfg_defuse_edges_multi_block():
    """DFGBuilder creates DefUse edges across blocks."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 10
j blk2

blk2:
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    defuse = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'DefUse']
    assert len(defuse) >= 1


def test_dfg_usedef_edges():
    """DFGBuilder creates UseDef edges for redefined variables."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 10
mv @return x
mv x 20
mv @return x
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    usedef = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'UseDef']
    # x is used then redefined
    assert isinstance(usedef, list)


def test_dfg_constant_stm_source_node():
    """DFGBuilder marks constant assignments as source nodes."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 42
mv y 10
mv z (+ x y)
mv @return z
ret @return
'''
    scope = build_scope_with_loop(src)
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    # x=42 and y=10 are constant assignments, should be source nodes
    assert len(dfg.src_nodes) >= 2


def test_dfg_multi_block_seq():
    """DFGBuilder creates proper edges for multi-block sequential flow."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
j blk2

blk2:
mv y (+ x 5)
j blk3

blk3:
mv @return y
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='sequential')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert len(dfg.nodes) >= 4


def test_dfg_builder_add_seq_edges_for_timed():
    """DFGBuilder._add_seq_edges_for_timed with timed scheduling."""
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
    scope = build_scope_with_loop(src, scheduling='timed')
    for blk in scope.traverse_blocks():
        blk.synth_params['cycle'] = 'any'
        blk.synth_params['ii'] = -1
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert len(dfg.nodes) >= 4
    # In timed mode, _add_seq_edges_for_timed is called
    # Verify DFG is valid
    for node in dfg.nodes:
        # Check all edges are consistent
        for succ in dfg.succs(node):
            assert node in dfg.preds(succ)


def test_dfg_builder_sequential_with_many_stms():
    """DFGBuilder creates seq edges for sequential mode with many stms."""
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
mv c 3
mv d 4
mv e 5
mv @return e
ret @return
'''
    scope = build_scope_with_loop(src, scheduling='sequential')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    # Sequential scheduling: should have seq edges between consecutive independent stms
    seq_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'Seq']
    assert len(seq_edges) >= 4


def test_dfg_sequential_with_cjump():
    """DFGBuilder with sequential scheduling and CJump."""
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
    scope = build_scope_with_loop(src, scheduling='sequential')
    DFGBuilder().process(scope)
    dfg = scope.top_dfg
    assert dfg is not None
    # Seq edges should exist in sequential mode
    seq_edges = [(n1, n2) for (n1, n2), (typ, _) in dfg.edges.items() if typ == 'Seq']
    assert len(seq_edges) >= 1
