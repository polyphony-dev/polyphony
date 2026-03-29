"""Tests for AHDLVisitor and AHDLCollector in ahdlvisitor.py."""
from collections import defaultdict

import pytest

from polyphony.compiler.ahdl.ahdl import (
    AHDL,
    AHDL_ASSIGN,
    AHDL_BLOCK,
    AHDL_CALLEE_EPILOG,
    AHDL_CALLEE_PROLOG,
    AHDL_CASE,
    AHDL_CASE_ITEM,
    AHDL_COMB,
    AHDL_CONCAT,
    AHDL_CONNECT,
    AHDL_CONST,
    AHDL_EVENT_TASK,
    AHDL_FUNCALL,
    AHDL_FUNCTION,
    AHDL_IF,
    AHDL_IF_EXP,
    AHDL_INLINE,
    AHDL_IO_READ,
    AHDL_IO_WRITE,
    AHDL_MEMVAR,
    AHDL_META_OP,
    AHDL_META_WAIT,
    AHDL_MODULECALL,
    AHDL_MOVE,
    AHDL_NOP,
    AHDL_OP,
    AHDL_PIPELINE_GUARD,
    AHDL_PROCCALL,
    AHDL_SEQ,
    AHDL_SLICE,
    AHDL_STM,
    AHDL_SUBSCRIPT,
    AHDL_SYMBOL,
    AHDL_TRANSITION,
    AHDL_TRANSITION_IF,
    AHDL_VAR,
    State,
)
from polyphony.compiler.ahdl.ahdlvisitor import AHDLCollector, AHDLVisitor
from polyphony.compiler.ahdl.hdlmodule import FSM, HDLModule
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

IR_SRC = """
scope test
tags function returnable
return int32

blk1:
ret @return
"""


def build_scope(src=IR_SRC):
    """Build a scope from IR source text."""
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule(scope):
    """Create a minimal HDLModule registered in env."""
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def make_signal(hdlscope, name, width=1, tags=None):
    """Create a signal via hdlscope.gen_sig."""
    if tags is None:
        tags = {'reg'}
    return hdlscope.gen_sig(name, width, tags)


def make_nop_block(name='blk'):
    """Return a simple AHDL_BLOCK containing one AHDL_NOP."""
    return AHDL_BLOCK(name, (AHDL_NOP('nop'),))


def make_stg_with_state(hdlmodule, stg_name='main', state_name='S0'):
    """Create a STG with a single state containing a NOP block."""
    stg = STG(stg_name, None, hdlmodule)
    block = make_nop_block()
    state = stg.new_state(state_name, block, 0)
    stg.set_states([state])
    return stg, state


def make_hdlmodule_with_scope():
    """Convenience: build scope + hdlmodule in one call."""
    scope = build_scope()
    return make_hdlmodule(scope), scope


# ============================================================
# Tracking visitor — records which visit_* methods were called
# ============================================================

class TrackingVisitor(AHDLVisitor):
    """AHDLVisitor subclass that records every visit_* call by class name."""

    def __init__(self):
        super().__init__()
        self.visited = []

    def visit(self, ahdl):
        self.visited.append(type(ahdl).__name__)
        return super().visit(ahdl)


# ============================================================
# Tests: AHDLVisitor.__init__
# ============================================================

def test_init_sets_none_fields():
    """AHDLVisitor initialises tracking fields to None."""
    setup_test()
    v = AHDLVisitor()
    assert v.current_fsm is None
    assert v.current_stg is None
    assert v.current_state is None
    assert v.current_stm is None


# ============================================================
# Tests: process / process_fsm / process_stg
# ============================================================

def test_process_empty_hdlmodule():
    """process() with no decls, no edge_detectors, and no fsms runs without error."""
    hdl, _ = make_hdlmodule_with_scope()
    v = AHDLVisitor()
    v.process(hdl)  # must not raise


def test_process_visits_decls():
    """process() visits every decl in hdlmodule.decls."""
    hdl, _ = make_hdlmodule_with_scope()
    sig_dst = make_signal(hdl, 'dst', tags={'net'})
    sig_src = make_signal(hdl, 'src', tags={'reg'})
    dst = AHDL_VAR(sig_dst, Ctx.STORE)
    src = AHDL_VAR(sig_src, Ctx.LOAD)
    assign = AHDL_ASSIGN(dst, src)
    hdl.add_decl(assign)

    v = TrackingVisitor()
    v.process(hdl)
    assert 'AHDL_ASSIGN' in v.visited


def test_process_visits_edge_detectors():
    """process() visits var/old/new in edge_detectors."""
    hdl, _ = make_hdlmodule_with_scope()
    sig = make_signal(hdl, 'clk', tags={'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    old = AHDL_CONST(0)
    new = AHDL_CONST(1)
    hdl.add_edge_detector(var, old, new)

    v = TrackingVisitor()
    v.process(hdl)
    # var (AHDL_VAR), old (AHDL_CONST), new (AHDL_CONST)
    assert 'AHDL_VAR' in v.visited
    assert v.visited.count('AHDL_CONST') >= 2


def test_process_visits_fsm_states():
    """process() traverses FSMs, STGs, and states."""
    hdl, scope = make_hdlmodule_with_scope()
    hdl.add_fsm('main_fsm', scope)
    stg, state = make_stg_with_state(hdl)
    hdl.add_fsm_stg('main_fsm', [stg])

    v = TrackingVisitor()
    v.process(hdl)
    assert 'State' in v.visited


def test_process_fsm_sets_current_fsm():
    """process_fsm() sets current_fsm and visits reset_stms."""
    hdl, scope = make_hdlmodule_with_scope()
    hdl.add_fsm('fsm0', scope)
    fsm = hdl.fsms['fsm0']
    sig = make_signal(hdl, 'x', tags={'reg'})
    reset_stm = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(0))
    fsm.reset_stms.append(reset_stm)
    stg, _ = make_stg_with_state(hdl)
    fsm.stgs.append(stg)

    v = AHDLVisitor()
    v.process_fsm(fsm)
    assert v.current_fsm is fsm


def test_process_fsm_visits_reset_stms():
    """process_fsm() visits all reset_stms before processing STGs."""
    hdl, scope = make_hdlmodule_with_scope()
    hdl.add_fsm('reset_fsm', scope)
    fsm = hdl.fsms['reset_fsm']

    sig = make_signal(hdl, 'rst_x', tags={'reg'})
    reset_stm = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(0))
    fsm.reset_stms.append(reset_stm)

    stg, _ = make_stg_with_state(hdl, stg_name='rst_stg')
    fsm.stgs.append(stg)

    v = TrackingVisitor()
    v.process_fsm(fsm)
    assert 'AHDL_MOVE' in v.visited
    assert 'AHDL_CONST' in v.visited


def test_process_stg_sets_current_stg():
    """process_stg() sets current_stg and visits each state."""
    hdl, _ = make_hdlmodule_with_scope()
    stg, state = make_stg_with_state(hdl)

    v = AHDLVisitor()
    v.process_stg(stg)
    assert v.current_stg is stg
    assert v.current_state is state


# ============================================================
# Tests: individual visit_* methods
# ============================================================

def test_visit_AHDL_CONST():
    """visit_AHDL_CONST is a no-op but must not raise."""
    setup_test()
    v = AHDLVisitor()
    v.visit(AHDL_CONST(42))


def test_visit_AHDL_OP():
    """visit_AHDL_OP visits each arg."""
    setup_test()
    v = TrackingVisitor()
    op = AHDL_OP('Add', AHDL_CONST(1), AHDL_CONST(2))
    v.visit(op)
    assert v.visited.count('AHDL_CONST') == 2


def test_visit_AHDL_META_OP_with_ahdl_and_non_ahdl_args():
    """visit_AHDL_META_OP visits AHDL args and skips non-AHDL ones."""
    setup_test()
    v = TrackingVisitor()
    # Mix of AHDL and non-AHDL args
    meta = AHDL_META_OP('some_op', AHDL_CONST(5), 'plain_string')
    v.visit(meta)
    assert 'AHDL_CONST' in v.visited
    # 'plain_string' should NOT have caused any visit
    assert v.visited.count('AHDL_CONST') == 1


def test_visit_AHDL_VAR():
    """visit_AHDL_VAR is a no-op but must not raise."""
    hdl, _ = make_hdlmodule_with_scope()
    sig = make_signal(hdl, 'v1')
    v = AHDLVisitor()
    v.visit(AHDL_VAR(sig, Ctx.LOAD))


def test_visit_AHDL_MEMVAR():
    """visit_AHDL_MEMVAR is a no-op but must not raise."""
    hdl, _ = make_hdlmodule_with_scope()
    sig = make_signal(hdl, 'mem1')
    v = AHDLVisitor()
    v.visit(AHDL_MEMVAR(sig, Ctx.LOAD))


def test_visit_AHDL_SUBSCRIPT():
    """visit_AHDL_SUBSCRIPT visits memvar and offset."""
    hdl, _ = make_hdlmodule_with_scope()
    sig = make_signal(hdl, 'arr')
    mv = AHDL_MEMVAR(sig, Ctx.LOAD)
    subscript = AHDL_SUBSCRIPT(mv, AHDL_CONST(0))
    v = TrackingVisitor()
    v.visit(subscript)
    assert 'AHDL_MEMVAR' in v.visited
    assert 'AHDL_CONST' in v.visited


def test_visit_AHDL_SYMBOL():
    """visit_AHDL_SYMBOL is a no-op but must not raise."""
    setup_test()
    v = AHDLVisitor()
    v.visit(AHDL_SYMBOL('my_sym'))


def test_visit_AHDL_CONCAT():
    """visit_AHDL_CONCAT visits each var in varlist."""
    hdl, _ = make_hdlmodule_with_scope()
    sig1 = make_signal(hdl, 'c1')
    sig2 = make_signal(hdl, 'c2')
    concat = AHDL_CONCAT((AHDL_VAR(sig1, Ctx.LOAD), AHDL_VAR(sig2, Ctx.LOAD)), None)
    v = TrackingVisitor()
    v.visit(concat)
    assert v.visited.count('AHDL_VAR') == 2


def test_visit_AHDL_SLICE():
    """visit_AHDL_SLICE visits var, hi, and lo."""
    hdl, _ = make_hdlmodule_with_scope()
    sig = make_signal(hdl, 'slc')
    var = AHDL_VAR(sig, Ctx.LOAD)
    slc = AHDL_SLICE(var, AHDL_CONST(7), AHDL_CONST(0))
    v = TrackingVisitor()
    v.visit(slc)
    assert 'AHDL_VAR' in v.visited
    assert v.visited.count('AHDL_CONST') == 2


def test_visit_AHDL_FUNCALL():
    """visit_AHDL_FUNCALL visits name var and each arg."""
    hdl, _ = make_hdlmodule_with_scope()
    sig = make_signal(hdl, 'fn_name')
    name_var = AHDL_VAR(sig, Ctx.LOAD)
    fcall = AHDL_FUNCALL(name_var, (AHDL_CONST(1), AHDL_CONST(2)))
    v = TrackingVisitor()
    v.visit(fcall)
    assert 'AHDL_VAR' in v.visited
    assert v.visited.count('AHDL_CONST') == 2


def test_visit_AHDL_IF_EXP():
    """visit_AHDL_IF_EXP visits cond, lexp, and rexp."""
    setup_test()
    ifexp = AHDL_IF_EXP(AHDL_CONST(1), AHDL_CONST(2), AHDL_CONST(3))
    v = TrackingVisitor()
    v.visit(ifexp)
    assert v.visited.count('AHDL_CONST') == 3


def test_visit_AHDL_BLOCK():
    """visit_AHDL_BLOCK visits each code in the block."""
    setup_test()
    block = AHDL_BLOCK('b', (AHDL_NOP('a'), AHDL_NOP('b')))
    v = TrackingVisitor()
    v.visit(block)
    assert v.visited.count('AHDL_NOP') == 2


def test_visit_AHDL_NOP():
    """visit_AHDL_NOP is a no-op."""
    setup_test()
    v = AHDLVisitor()
    v.visit(AHDL_NOP('info'))


def test_visit_AHDL_INLINE():
    """visit_AHDL_INLINE is a no-op."""
    setup_test()
    v = AHDLVisitor()
    v.visit(AHDL_INLINE('$display();'))


def test_visit_AHDL_MOVE():
    """visit_AHDL_MOVE visits src and dst."""
    hdl, _ = make_hdlmodule_with_scope()
    sig_dst = make_signal(hdl, 'dst_m', tags={'reg'})
    sig_src = make_signal(hdl, 'src_m', tags={'reg'})
    move = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_VAR(sig_src, Ctx.LOAD))
    v = TrackingVisitor()
    v.visit(move)
    assert v.visited.count('AHDL_VAR') == 2


def test_visit_AHDL_ASSIGN():
    """visit_AHDL_ASSIGN visits src and dst."""
    hdl, _ = make_hdlmodule_with_scope()
    sig_dst = make_signal(hdl, 'asgn_dst', tags={'net'})
    sig_src = make_signal(hdl, 'asgn_src', tags={'reg'})
    assign = AHDL_ASSIGN(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_VAR(sig_src, Ctx.LOAD))
    v = TrackingVisitor()
    v.visit(assign)
    assert v.visited.count('AHDL_VAR') == 2


def test_visit_AHDL_FUNCTION():
    """visit_AHDL_FUNCTION visits output, inputs, and stms."""
    hdl, _ = make_hdlmodule_with_scope()
    sig_out = make_signal(hdl, 'fn_out', tags={'net'})
    sig_in = make_signal(hdl, 'fn_in', tags={'reg'})
    output = AHDL_VAR(sig_out, Ctx.STORE)
    inp = AHDL_VAR(sig_in, Ctx.LOAD)
    nop = AHDL_NOP('body')
    func = AHDL_FUNCTION(output, (inp,), (nop,))
    v = TrackingVisitor()
    v.visit(func)
    assert 'AHDL_VAR' in v.visited
    assert 'AHDL_NOP' in v.visited


def test_visit_AHDL_COMB():
    """visit_AHDL_COMB visits each statement."""
    setup_test()
    comb = AHDL_COMB('comb0', (AHDL_NOP('x'),))
    v = TrackingVisitor()
    v.visit(comb)
    assert 'AHDL_NOP' in v.visited


def test_visit_AHDL_EVENT_TASK():
    """visit_AHDL_EVENT_TASK visits its stm."""
    setup_test()
    task = AHDL_EVENT_TASK((), AHDL_NOP('evt'))
    v = TrackingVisitor()
    v.visit(task)
    assert 'AHDL_NOP' in v.visited


def test_visit_AHDL_CONNECT():
    """visit_AHDL_CONNECT visits src and dst."""
    hdl, _ = make_hdlmodule_with_scope()
    sig1 = make_signal(hdl, 'con_dst', tags={'net'})
    sig2 = make_signal(hdl, 'con_src', tags={'reg'})
    conn = AHDL_CONNECT(AHDL_VAR(sig1, Ctx.LOAD), AHDL_VAR(sig2, Ctx.LOAD))
    v = TrackingVisitor()
    v.visit(conn)
    assert v.visited.count('AHDL_VAR') == 2


def test_visit_AHDL_IO_READ_with_dst():
    """visit_AHDL_IO_READ visits io and dst when dst is not None."""
    hdl, _ = make_hdlmodule_with_scope()
    sig_io = make_signal(hdl, 'io_r', tags={'reg'})
    sig_dst = make_signal(hdl, 'io_dst', tags={'reg'})
    io_var = AHDL_VAR(sig_io, Ctx.LOAD)
    dst_var = AHDL_VAR(sig_dst, Ctx.STORE)
    rd = AHDL_IO_READ(io_var, dst_var, False)
    v = TrackingVisitor()
    v.visit(rd)
    assert v.visited.count('AHDL_VAR') == 2


def test_visit_AHDL_IO_READ_without_dst():
    """visit_AHDL_IO_READ visits only io when dst is None."""
    hdl, _ = make_hdlmodule_with_scope()
    sig_io = make_signal(hdl, 'io_r2', tags={'reg'})
    io_var = AHDL_VAR(sig_io, Ctx.LOAD)
    rd = AHDL_IO_READ(io_var, None, False)
    v = TrackingVisitor()
    v.visit(rd)
    assert v.visited.count('AHDL_VAR') == 1


def test_visit_AHDL_IO_WRITE():
    """visit_AHDL_IO_WRITE visits io and src."""
    hdl, _ = make_hdlmodule_with_scope()
    sig_io = make_signal(hdl, 'io_w', tags={'reg'})
    io_var = AHDL_VAR(sig_io, Ctx.LOAD)
    wr = AHDL_IO_WRITE(io_var, AHDL_CONST(1), False)
    v = TrackingVisitor()
    v.visit(wr)
    assert 'AHDL_VAR' in v.visited
    assert 'AHDL_CONST' in v.visited


def test_visit_AHDL_SEQ():
    """visit_AHDL_SEQ dispatches to the factor's visitor method directly (not via self.visit)."""
    setup_test()
    nop = AHDL_NOP('seq_factor')
    seq = AHDL_SEQ(nop, 0, 1)

    # visit_AHDL_SEQ calls visitor(ahdl.factor) directly, bypassing self.visit().
    # Use a spy on visit_AHDL_NOP to confirm the factor's visitor is called.
    nop_called = []

    class SpyVisitor(AHDLVisitor):
        def visit_AHDL_NOP(self, ahdl):
            nop_called.append(ahdl)

    v = SpyVisitor()
    v.visit(seq)
    assert len(nop_called) == 1
    assert nop_called[0] is nop


def test_visit_AHDL_IF_single_branch():
    """visit_AHDL_IF visits cond and block for a single branch."""
    setup_test()
    cond = AHDL_CONST(1)
    block = AHDL_BLOCK('if_blk', (AHDL_NOP('then'),))
    aif = AHDL_IF((cond,), (block,))
    v = TrackingVisitor()
    v.visit(aif)
    assert 'AHDL_CONST' in v.visited
    assert 'AHDL_BLOCK' in v.visited


def test_visit_AHDL_IF_with_else_branch():
    """visit_AHDL_IF with None cond (else branch) visits all blocks."""
    setup_test()
    cond = AHDL_CONST(1)
    block_then = AHDL_BLOCK('then', (AHDL_NOP('t'),))
    block_else = AHDL_BLOCK('else', (AHDL_NOP('e'),))
    aif = AHDL_IF((cond, None), (block_then, block_else))
    v = TrackingVisitor()
    v.visit(aif)
    assert v.visited.count('AHDL_NOP') == 2


def test_visit_AHDL_MODULECALL():
    """visit_AHDL_MODULECALL visits each arg."""
    setup_test()
    mc = AHDL_MODULECALL(None, (AHDL_CONST(1), AHDL_CONST(2)), 'inst', 'pfx', ())
    v = TrackingVisitor()
    v.visit(mc)
    assert v.visited.count('AHDL_CONST') == 2


def test_visit_AHDL_CALLEE_PROLOG():
    """visit_AHDL_CALLEE_PROLOG is a no-op."""
    setup_test()
    v = AHDLVisitor()
    v.visit(AHDL_CALLEE_PROLOG('fn'))


def test_visit_AHDL_CALLEE_EPILOG():
    """visit_AHDL_CALLEE_EPILOG is a no-op."""
    setup_test()
    v = AHDLVisitor()
    v.visit(AHDL_CALLEE_EPILOG('fn'))


def test_visit_AHDL_PROCCALL():
    """visit_AHDL_PROCCALL visits each arg."""
    setup_test()
    pc = AHDL_PROCCALL('proc', (AHDL_CONST(3),))
    v = TrackingVisitor()
    v.visit(pc)
    assert 'AHDL_CONST' in v.visited


def test_visit_AHDL_META_WAIT_with_ahdl_arg():
    """visit_AHDL_META_WAIT visits AHDL args only, skips non-AHDL."""
    setup_test()
    mw = AHDL_META_WAIT('WAIT', AHDL_CONST(5), 'non_ahdl')
    v = TrackingVisitor()
    v.visit(mw)
    assert 'AHDL_CONST' in v.visited
    assert v.visited.count('AHDL_CONST') == 1


def test_visit_AHDL_CASE_ITEM():
    """visit_AHDL_CASE_ITEM visits val and block."""
    setup_test()
    item = AHDL_CASE_ITEM(AHDL_CONST(0), AHDL_BLOCK('ci', (AHDL_NOP('n'),)))
    v = TrackingVisitor()
    v.visit(item)
    assert 'AHDL_CONST' in v.visited
    assert 'AHDL_BLOCK' in v.visited


def test_visit_AHDL_CASE():
    """visit_AHDL_CASE visits sel and all items."""
    hdl, _ = make_hdlmodule_with_scope()
    sig = make_signal(hdl, 'sel_sig', tags={'reg'})
    sel = AHDL_VAR(sig, Ctx.LOAD)
    item = AHDL_CASE_ITEM(AHDL_CONST(0), AHDL_BLOCK('ci', (AHDL_NOP('n'),)))
    case = AHDL_CASE(sel, (item,))
    v = TrackingVisitor()
    v.visit(case)
    assert 'AHDL_VAR' in v.visited
    assert 'AHDL_CASE_ITEM' in v.visited


def test_visit_AHDL_TRANSITION():
    """visit_AHDL_TRANSITION is a no-op."""
    setup_test()
    v = AHDLVisitor()
    v.visit(AHDL_TRANSITION('S1'))


def test_visit_AHDL_TRANSITION_IF():
    """visit_AHDL_TRANSITION_IF delegates to visit_AHDL_IF."""
    setup_test()
    cond = AHDL_CONST(1)
    block = AHDL_BLOCK('tif', (AHDL_NOP('x'),))
    tif = AHDL_TRANSITION_IF((cond,), (block,))
    v = TrackingVisitor()
    v.visit(tif)
    assert 'AHDL_BLOCK' in v.visited
    assert 'AHDL_CONST' in v.visited


def test_visit_AHDL_PIPELINE_GUARD():
    """visit_AHDL_PIPELINE_GUARD delegates to visit_AHDL_IF."""
    setup_test()
    cond = AHDL_CONST(1)
    nop = AHDL_NOP('pg')
    guard = AHDL_PIPELINE_GUARD(cond, (nop,))
    v = TrackingVisitor()
    v.visit(guard)
    assert 'AHDL_BLOCK' in v.visited


def test_visit_State():
    """visit_State sets current_state and visits the block."""
    hdl, _ = make_hdlmodule_with_scope()
    stg, state = make_stg_with_state(hdl)
    v = TrackingVisitor()
    v.visit(state)
    assert v.current_state is state
    assert 'AHDL_BLOCK' in v.visited


# ============================================================
# Tests: find_visitor with inheritance lookup
# ============================================================

def test_find_visitor_direct_match():
    """find_visitor returns the direct visitor for a known class."""
    setup_test()
    v = AHDLVisitor()
    visitor_fn = v.find_visitor(AHDL_CONST)
    assert visitor_fn is not None
    assert visitor_fn == v.visit_AHDL_CONST


def test_find_visitor_base_class_fallback():
    """find_visitor walks the MRO and finds a visitor via base class."""
    setup_test()

    # AHDL_MEMVAR extends AHDL_VAR; if we make a subclass of AHDL_CONST with
    # no dedicated visitor method, find_visitor should fall back to AHDL_CONST's.
    class AHDL_CONST_SUBCLASS(AHDL_CONST):
        pass

    v = AHDLVisitor()
    visitor_fn = v.find_visitor(AHDL_CONST_SUBCLASS)
    assert visitor_fn is not None
    # Must ultimately delegate to visit_AHDL_CONST
    assert visitor_fn == v.visit_AHDL_CONST


# ============================================================
# Tests: visit() updates current_stm for AHDL_STM nodes
# ============================================================

def test_visit_sets_current_stm():
    """visit() updates current_stm when visiting an AHDL_STM subclass."""
    setup_test()
    v = AHDLVisitor()
    nop = AHDL_NOP('stm_track')
    v.visit(nop)
    assert v.current_stm is nop


def test_visit_does_not_change_current_stm_for_exp():
    """visit() must NOT update current_stm for non-STM nodes (AHDL_EXP)."""
    setup_test()
    v = AHDLVisitor()
    nop = AHDL_NOP('initial')
    v.visit(nop)
    # Now visit a pure expression — current_stm should stay as nop
    v.visit(AHDL_CONST(99))
    assert v.current_stm is nop


# ============================================================
# Tests: AHDLCollector
# ============================================================

def test_ahdl_collector_collects_target_class():
    """AHDLCollector gathers all instances of the target AHDL class."""
    hdl, scope = make_hdlmodule_with_scope()
    hdl.add_fsm('fsm_col', scope)
    stg, state = make_stg_with_state(hdl, state_name='CS0')
    hdl.add_fsm_stg('fsm_col', [stg])

    collector = AHDLCollector(AHDL_NOP)
    collector.process(hdl)

    all_results = list(collector.results.values())
    assert len(all_results) > 0
    flat = [item for items in all_results for item in items]
    assert all(isinstance(item, AHDL_NOP) for item in flat)


def test_ahdl_collector_does_not_collect_other_classes():
    """AHDLCollector ignores AHDL nodes that are not the target class."""
    hdl, scope = make_hdlmodule_with_scope()
    hdl.add_fsm('fsm_col2', scope)
    stg, state = make_stg_with_state(hdl, state_name='CS1')
    hdl.add_fsm_stg('fsm_col2', [stg])

    # Collect AHDL_CONST — none present in the simple NOP block
    collector = AHDLCollector(AHDL_CONST)
    collector.process(hdl)

    flat = [item for items in collector.results.values() for item in items]
    assert flat == []


def test_ahdl_collector_keyed_by_current_state():
    """AHDLCollector keys results by the current state at time of collection."""
    hdl, scope = make_hdlmodule_with_scope()
    hdl.add_fsm('fsm_col3', scope)
    stg, state = make_stg_with_state(hdl, state_name='CS2')
    hdl.add_fsm_stg('fsm_col3', [stg])

    collector = AHDLCollector(AHDL_NOP)
    collector.process(hdl)

    assert state in collector.results
    assert len(collector.results[state]) == 1
    assert isinstance(collector.results[state][0], AHDL_NOP)


def test_ahdl_collector_multiple_states():
    """AHDLCollector distinguishes nodes from different states."""
    hdl, scope = make_hdlmodule_with_scope()
    hdl.add_fsm('fsm_col4', scope)

    stg = STG('main', None, hdl)
    block0 = AHDL_BLOCK('b0', (AHDL_NOP('n0'),))
    block1 = AHDL_BLOCK('b1', (AHDL_NOP('n1'), AHDL_NOP('n2')))
    state0 = stg.new_state('SA', block0, 0)
    state1 = stg.new_state('SB', block1, 1)
    stg.set_states([state0, state1])
    hdl.add_fsm_stg('fsm_col4', [stg])

    collector = AHDLCollector(AHDL_NOP)
    collector.process(hdl)

    assert len(collector.results[state0]) == 1
    assert len(collector.results[state1]) == 2


def test_ahdl_collector_inherits_from_ahdl_visitor():
    """AHDLCollector is a subclass of AHDLVisitor."""
    setup_test()
    collector = AHDLCollector(AHDL_CONST)
    assert isinstance(collector, AHDLVisitor)


def test_ahdl_collector_results_is_defaultdict():
    """AHDLCollector.results is a defaultdict(list) initialised empty."""
    setup_test()
    collector = AHDLCollector(AHDL_NOP)
    assert isinstance(collector.results, defaultdict)
    assert len(collector.results) == 0
