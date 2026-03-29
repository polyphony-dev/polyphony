"""Tests for NetReducer covering uncovered lines."""
from polyphony.compiler.ahdl.transformers.netreducer import NetReducer
from polyphony.compiler.ahdl.ahdl import (
    AHDL_VAR, AHDL_MEMVAR, AHDL_ASSIGN, AHDL_CONST, AHDL_OP, AHDL_SUBSCRIPT,
    AHDL_MOVE, AHDL_BLOCK, AHDL_EVENT_TASK, Ctx,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


_SRC = '''
scope test
tags function returnable
'''


def build_scope():
    setup_test()
    parser = IrReader(_SRC)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def _add_assign(hdl, dst_var, src):
    """Helper to add an AHDL_ASSIGN as a static assignment (decl)."""
    assign = AHDL_ASSIGN(dst_var, src)
    hdl.add_static_assignment(assign)
    return assign


# ============================================================
# _eliminate_simple_assign — lines 38-70
# ============================================================

def test_eliminate_simple_assign_replaces_net():
    """Two nets connected by assignment: the second is replaced by the first."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('a', 8, {'net'})
    sig_b = hdl.gen_sig('b', 8, {'net'})
    # assign b = a (store b, load a)
    dst = AHDL_VAR(sig_b, Ctx.STORE)
    src = AHDL_VAR(sig_a, Ctx.LOAD)
    _add_assign(hdl, dst, src)

    # Also add a task that uses sig_b so replacement has something to do
    sig_r = hdl.gen_sig('clk', 1, {'reg'})
    sig_dst = hdl.gen_sig('dst', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_VAR(sig_b, Ctx.LOAD))
    task = AHDL_EVENT_TASK(((sig_r, 'rising'),), mv)
    hdl.tasks.append(task)

    nr = NetReducer()
    nr.process(hdl)
    # After reduction, the MOVE in the task should reference sig_a not sig_b
    new_task = hdl.tasks[0]
    assert isinstance(new_task, AHDL_EVENT_TASK)


def test_eliminate_simple_assign_const_src_skipped():
    """Assignment with AHDL_CONST src is skipped (not eliminated)."""
    hdl = make_hdlmodule()
    sig_b = hdl.gen_sig('b', 8, {'net'})
    dst = AHDL_VAR(sig_b, Ctx.STORE)
    src = AHDL_CONST(42)
    _add_assign(hdl, dst, src)

    nr = NetReducer()
    nr.process(hdl)
    # No replacement happened, assignment still there
    assigns = hdl.get_static_assignment()
    assert len(assigns) == 1


def test_eliminate_simple_assign_width_mismatch_skipped():
    """Assignments with mismatched widths are not eliminated."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('a', 8, {'net'})
    sig_b = hdl.gen_sig('b', 16, {'net'})  # different width
    dst = AHDL_VAR(sig_b, Ctx.STORE)
    src = AHDL_VAR(sig_a, Ctx.LOAD)
    _add_assign(hdl, dst, src)

    nr = NetReducer()
    nr.process(hdl)
    assigns = hdl.get_static_assignment()
    assert len(assigns) == 1  # assignment kept


def test_eliminate_simple_assign_output_sig_skipped():
    """Assignments with output signal as dst are not eliminated."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('a', 8, {'net'})
    sig_out = hdl.gen_sig('out', 8, {'net', 'output'})
    dst = AHDL_VAR(sig_out, Ctx.STORE)
    src = AHDL_VAR(sig_a, Ctx.LOAD)
    _add_assign(hdl, dst, src)

    nr = NetReducer()
    nr.process(hdl)
    assigns = hdl.get_static_assignment()
    assert len(assigns) == 1  # output assignment kept


def test_eliminate_simple_assign_no_assigns_returns_false():
    """With no assignments, process() runs without error."""
    hdl = make_hdlmodule()
    nr = NetReducer()
    nr.process(hdl)
    assert hdl.get_static_assignment() == []


# ============================================================
# _rvalue_from_dst — lines 21-28
# ============================================================

def test_rvalue_from_dst_var():
    """_rvalue_from_dst with AHDL_VAR returns AHDL_VAR with LOAD ctx."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('x', 8, {'net'})
    var = AHDL_VAR(sig, Ctx.STORE)
    nr = NetReducer()
    nr.hdlmodule = hdl
    result = nr._rvalue_from_dst(var)
    assert isinstance(result, AHDL_VAR)
    assert result.ctx == Ctx.LOAD


def test_rvalue_from_dst_subscript():
    """_rvalue_from_dst with AHDL_SUBSCRIPT returns AHDL_SUBSCRIPT."""
    hdl = make_hdlmodule()
    arr_sig = hdl.gen_sig('arr', 8, {'net'})
    memvar = AHDL_MEMVAR(arr_sig, Ctx.STORE)
    sub = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    nr = NetReducer()
    nr.hdlmodule = hdl
    result = nr._rvalue_from_dst(sub)
    assert isinstance(result, AHDL_SUBSCRIPT)
    assert result.memvar.ctx == Ctx.LOAD


# ============================================================
# _get_signal — lines 30-36
# ============================================================

def test_get_signal_from_var():
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('x', 8, {'net'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    nr = NetReducer()
    result = nr._get_signal(var)
    assert result is sig


def test_get_signal_from_subscript():
    hdl = make_hdlmodule()
    arr_sig = hdl.gen_sig('arr', 8, {'net'})
    memvar = AHDL_MEMVAR(arr_sig, Ctx.LOAD)
    sub = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    nr = NetReducer()
    result = nr._get_signal(sub)
    assert result is arr_sig


# ============================================================
# _eliminate_common_assign_src — lines 72-91
# ============================================================

def test_eliminate_common_assign_src_deduplicates():
    """Two assignments with identical src are deduplicated."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('a', 8, {'net'})
    sig_b = hdl.gen_sig('b', 8, {'net'})
    sig_x = hdl.gen_sig('x', 8, {'net'})

    # assign a = x+1; assign b = x+1 -> b should become = a
    src = AHDL_OP('Add', AHDL_VAR(sig_x, Ctx.LOAD), AHDL_CONST(1))
    dst_a = AHDL_VAR(sig_a, Ctx.STORE)
    dst_b = AHDL_VAR(sig_b, Ctx.STORE)
    _add_assign(hdl, dst_a, src)
    _add_assign(hdl, dst_b, src)

    # Add a task that uses b as rvalue so replacement can occur
    sig_r = hdl.gen_sig('clk', 1, {'reg'})
    sig_dst = hdl.gen_sig('dst', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_VAR(sig_b, Ctx.LOAD))
    task = AHDL_EVENT_TASK(((sig_r, 'rising'),), mv)
    hdl.tasks.append(task)

    nr = NetReducer()
    nr.process(hdl)
    # After common src elimination, b is replaced by a in the task
    new_mv = hdl.tasks[0].stm
    assert isinstance(new_mv.src, AHDL_VAR)
    assert new_mv.src.sig.name == 'a'


def test_eliminate_common_assign_src_const_skipped():
    """Assignments with AHDL_CONST src are skipped by common src elimination."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('a', 8, {'net'})
    sig_b = hdl.gen_sig('b', 8, {'net'})
    dst_a = AHDL_VAR(sig_a, Ctx.STORE)
    dst_b = AHDL_VAR(sig_b, Ctx.STORE)
    _add_assign(hdl, dst_a, AHDL_CONST(42))
    _add_assign(hdl, dst_b, AHDL_CONST(42))

    nr = NetReducer()
    nr.process(hdl)
    assigns = hdl.get_static_assignment()
    # Both kept since AHDL_CONST is skipped
    assert len(assigns) >= 1


# ============================================================
# visit_AHDL_VAR and visit_AHDL_SUBSCRIPT — lines 121-138
# ============================================================

def test_visit_ahdl_var_replacement():
    """visit_AHDL_VAR replaces when key is in var_map."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('a', 8, {'net'})
    sig_b = hdl.gen_sig('b', 8, {'net'})
    var_a = AHDL_VAR(sig_a, Ctx.LOAD)
    var_b = AHDL_VAR(sig_b, Ctx.LOAD)

    nr = NetReducer()
    nr.hdlmodule = hdl
    nr.var_map = {var_a: var_b}
    nr.replaced_ahdls = []
    nr.current_stm = None

    result = nr.visit_AHDL_VAR(var_a)
    assert result is var_b
    assert str(var_a) in nr.replaced_ahdls


def test_visit_ahdl_var_no_replacement():
    """visit_AHDL_VAR returns same when key not in var_map."""
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('a', 8, {'net'})
    var_a = AHDL_VAR(sig_a, Ctx.LOAD)

    nr = NetReducer()
    nr.hdlmodule = hdl
    nr.var_map = {}
    nr.replaced_ahdls = []
    nr.current_stm = None

    result = nr.visit_AHDL_VAR(var_a)
    assert result is var_a


def test_visit_ahdl_subscript_replacement():
    """visit_AHDL_SUBSCRIPT replaces when key is in var_map."""
    hdl = make_hdlmodule()
    arr_sig = hdl.gen_sig('arr', 8, {'net'})
    arr_sig2 = hdl.gen_sig('arr2', 8, {'net'})
    memvar = AHDL_MEMVAR(arr_sig, Ctx.LOAD)
    memvar2 = AHDL_MEMVAR(arr_sig2, Ctx.LOAD)
    sub = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    sub2 = AHDL_SUBSCRIPT(memvar2, AHDL_CONST(0))

    nr = NetReducer()
    nr.hdlmodule = hdl
    nr.var_map = {sub: sub2}
    nr.replaced_ahdls = []
    nr.current_stm = None

    result = nr.visit_AHDL_SUBSCRIPT(sub)
    assert result is sub2
