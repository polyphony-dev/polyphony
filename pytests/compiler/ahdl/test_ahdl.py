"""Tests covering uncovered lines in polyphony/compiler/ahdl/ahdl.py."""
import pytest
from polyphony.compiler.ahdl.ahdl import (
    AHDL, AHDL_BLOCK, AHDL_CONST, AHDL_IF, AHDL_MOVE, AHDL_NOP, AHDL_OP,
    AHDL_PROCCALL, AHDL_SEQ, AHDL_SUBSCRIPT, AHDL_TRANSITION,
    AHDL_TRANSITION_IF, AHDL_VAR, AHDL_MEMVAR, State, AHDL_META_OP,
    AHDL_SYMBOL, AHDL_CONCAT, AHDL_SLICE, AHDL_FUNCALL, AHDL_IF_EXP,
    AHDL_INLINE, AHDL_ASSIGN, AHDL_FUNCTION, AHDL_COMB, AHDL_EVENT_TASK,
    AHDL_CONNECT, AHDL_IO_READ, AHDL_IO_WRITE, AHDL_MODULECALL,
    AHDL_CALLEE_PROLOG, AHDL_CALLEE_EPILOG, AHDL_META_WAIT,
    AHDL_CASE_ITEM, AHDL_CASE, AHDL_PIPELINE_GUARD,
)
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test

# IR text used to create a minimal scope for HDLModule
_MINIMAL_SCOPE_SRC = """
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
"""


def _make_scope_and_hdl():
    """Create a scope and HDLModule registered with env."""
    setup_test()
    parser = IrReader(_MINIMAL_SCOPE_SRC)
    parser.parse_scope()
    scope = None
    for name in parser.sources:
        scope = env.scopes[name]
        break
    assert scope is not None
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return scope, hdl


@pytest.fixture
def hdl():
    """Provide an HDLModule for signal creation."""
    _, h = _make_scope_and_hdl()
    return h


def make_reg_sig(hdl, name, width=8):
    return hdl.gen_sig(name, width, {'reg'})


def make_net_sig(hdl, name, width=8):
    return hdl.gen_sig(name, width, {'net'})


# ============================================================
# AHDL_CONST
# ============================================================

def test_ahdl_const_str_int():
    c = AHDL_CONST(42)
    assert str(c) == '42'


def test_ahdl_const_str_str():
    c = AHDL_CONST('hello')
    assert str(c) == 'hello'


# ============================================================
# AHDL_OP
# ============================================================

def test_ahdl_op_binary_str():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    op = AHDL_OP('Add', a, b)
    assert str(op) == '(1 + 2)'


def test_ahdl_op_unary_str():
    a = AHDL_CONST(5)
    op = AHDL_OP('USub', a)
    assert str(op) == '(-5)'


def test_ahdl_op_three_args_str():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    c = AHDL_CONST(3)
    op = AHDL_OP('Add', a, b, c)
    assert str(op) == '(1 + 2 + 3)'


def test_ahdl_op_is_relop_true():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    op = AHDL_OP('Eq', a, b)
    assert op.is_relop() is True


def test_ahdl_op_is_relop_all_ops():
    a = AHDL_CONST(0)
    b = AHDL_CONST(1)
    for relop in ('And', 'Or', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE', 'Is', 'IsNot'):
        op = AHDL_OP(relop, a, b)
        assert op.is_relop() is True, f"{relop} should be relop"


def test_ahdl_op_is_relop_false():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    op = AHDL_OP('Add', a, b)
    assert op.is_relop() is False


def test_ahdl_op_is_unop_true():
    a = AHDL_CONST(1)
    for unop in ('USub', 'UAdd', 'Not', 'Invert'):
        op = AHDL_OP(unop, a)
        assert op.is_unop() is True, f"{unop} should be unop"


def test_ahdl_op_is_unop_false():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    op = AHDL_OP('Add', a, b)
    assert op.is_unop() is False


# ============================================================
# AHDL_META_OP
# ============================================================

def test_ahdl_meta_op_str():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    meta = AHDL_META_OP('some_op', a, b)
    assert str(meta) == '(some_op 1, 2)'


def test_ahdl_meta_op_str_single():
    a = AHDL_CONST(7)
    meta = AHDL_META_OP('op', a)
    assert str(meta) == '(op 7)'


# ============================================================
# AHDL_VAR
# ============================================================

def test_ahdl_var_single_sig_str(hdl):
    sig = make_reg_sig(hdl, 'myvar')
    var = AHDL_VAR(sig, Ctx.LOAD)
    assert str(var) == 'myvar'


def test_ahdl_var_name_property(hdl):
    sig = make_reg_sig(hdl, 'myvar2')
    var = AHDL_VAR(sig, Ctx.LOAD)
    assert var.name == 'myvar2'


def test_ahdl_var_hdl_name_property_single(hdl):
    sig = make_reg_sig(hdl, 'myvar3')
    var = AHDL_VAR(sig, Ctx.LOAD)
    assert var.hdl_name == 'myvar3'


def test_ahdl_var_is_local_var_single(hdl):
    sig = make_reg_sig(hdl, 'v1')
    var = AHDL_VAR(sig, Ctx.LOAD)
    assert var.is_local_var() is True


def test_ahdl_var_tuple_input_str(hdl):
    """AHDL_VAR initialized with a tuple of signals produces dot-joined str."""
    sig1 = make_reg_sig(hdl, 'ta')
    sig2 = make_reg_sig(hdl, 'tb')
    var = AHDL_VAR((sig1, sig2), Ctx.LOAD)
    assert str(var) == 'ta.tb'


def test_ahdl_var_tuple_hdl_name(hdl):
    sig1 = make_reg_sig(hdl, 'ha')
    sig2 = make_reg_sig(hdl, 'hb')
    var = AHDL_VAR((sig1, sig2), Ctx.LOAD)
    assert var.hdl_name == 'ha_hb'


def test_ahdl_var_tuple_not_local(hdl):
    sig1 = make_reg_sig(hdl, 'nl1')
    sig2 = make_reg_sig(hdl, 'nl2')
    var = AHDL_VAR((sig1, sig2), Ctx.LOAD)
    assert var.is_local_var() is False


# ============================================================
# AHDL_MEMVAR
# ============================================================

def test_ahdl_memvar_str(hdl):
    sig = make_reg_sig(hdl, 'mem', 16)
    mvar = AHDL_MEMVAR(sig, Ctx.LOAD)
    assert str(mvar) == 'mem[16]'


def test_ahdl_memvar_str_tuple(hdl):
    sig1 = make_reg_sig(hdl, 'mp')
    sig2 = make_reg_sig(hdl, 'mq', 32)
    mvar = AHDL_MEMVAR((sig1, sig2), Ctx.LOAD)
    assert str(mvar) == 'mp.mq[32]'


# ============================================================
# AHDL_SUBSCRIPT
# ============================================================

def test_ahdl_subscript_str(hdl):
    sig = make_reg_sig(hdl, 'arr', 8)
    mvar = AHDL_MEMVAR(sig, Ctx.LOAD)
    offset = AHDL_CONST(3)
    sub = AHDL_SUBSCRIPT(mvar, offset)
    assert str(sub) == 'arr[8][3]'


def test_ahdl_subscript_ctx_load(hdl):
    sig = make_reg_sig(hdl, 'arr_ld', 8)
    mvar = AHDL_MEMVAR(sig, Ctx.LOAD)
    sub = AHDL_SUBSCRIPT(mvar, AHDL_CONST(0))
    assert sub.ctx == Ctx.LOAD


def test_ahdl_subscript_ctx_store(hdl):
    sig = make_reg_sig(hdl, 'arr_st', 8)
    mvar = AHDL_MEMVAR(sig, Ctx.STORE)
    sub = AHDL_SUBSCRIPT(mvar, AHDL_CONST(0))
    assert sub.ctx == Ctx.STORE


# ============================================================
# AHDL_SYMBOL
# ============================================================

def test_ahdl_symbol_str():
    sym = AHDL_SYMBOL('my_symbol')
    assert str(sym) == 'my_symbol'


# ============================================================
# AHDL_CONCAT
# ============================================================

def test_ahdl_concat_str_no_op():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    concat = AHDL_CONCAT((a, b), None)
    assert str(concat) == '{1, 2}'


def test_ahdl_concat_str_with_op():
    a = AHDL_CONST(3)
    b = AHDL_CONST(4)
    concat = AHDL_CONCAT((a, b), 'BitOr')
    # PYTHON_OP_2_HDL_OP_MAP maps 'BitOr' -> '|' (no spaces); join is literal
    assert str(concat) == '{3|4}'


# ============================================================
# AHDL_SLICE
# ============================================================

def test_ahdl_slice_str(hdl):
    sig = make_reg_sig(hdl, 'slc', 8)
    var = AHDL_VAR(sig, Ctx.LOAD)
    hi = AHDL_CONST(7)
    lo = AHDL_CONST(0)
    slc = AHDL_SLICE(var, hi, lo)
    assert str(slc) == 'slc[7:0]'


# ============================================================
# AHDL_FUNCALL
# ============================================================

def test_ahdl_funcall_str_no_args(hdl):
    sig = make_reg_sig(hdl, 'fn', 1)
    var = AHDL_VAR(sig, Ctx.LOAD)
    fc = AHDL_FUNCALL(var, ())
    assert str(fc) == 'fn()'


def test_ahdl_funcall_str_with_args(hdl):
    sig = make_reg_sig(hdl, 'fn2', 1)
    var = AHDL_VAR(sig, Ctx.LOAD)
    fc = AHDL_FUNCALL(var, (AHDL_CONST(1), AHDL_CONST(2)))
    assert str(fc) == 'fn2(1, 2)'


# ============================================================
# AHDL_IF_EXP
# ============================================================

def test_ahdl_if_exp_str():
    cond = AHDL_CONST(1)
    lexp = AHDL_CONST(10)
    rexp = AHDL_CONST(20)
    ie = AHDL_IF_EXP(cond, lexp, rexp)
    assert str(ie) == '1 ? 10 : 20'


# ============================================================
# AHDL_BLOCK
# ============================================================

def test_ahdl_block_str():
    nop = AHDL_NOP('nothing')
    blk = AHDL_BLOCK('b', (nop,))
    s = str(blk)
    assert '{\n' in s
    assert "nop('nothing')" in s
    assert '}\n' in s


def test_ahdl_block_post_init_rejects_list():
    with pytest.raises(AssertionError):
        AHDL_BLOCK('b', [AHDL_NOP('x')])  # type: ignore[arg-type]


def test_ahdl_block_traverse_flat():
    nop1 = AHDL_NOP('a')
    nop2 = AHDL_NOP('b')
    blk = AHDL_BLOCK('b', (nop1, nop2))
    result = blk.traverse()
    assert result == [nop1, nop2]


def test_ahdl_block_traverse_nested():
    nop1 = AHDL_NOP('inner')
    inner = AHDL_BLOCK('inner', (nop1,))
    nop2 = AHDL_NOP('outer')
    outer = AHDL_BLOCK('outer', (inner, nop2))
    result = outer.traverse()
    assert result == [nop1, nop2]


def test_ahdl_block_traverse_deeply_nested():
    nop = AHDL_NOP('deep')
    blk1 = AHDL_BLOCK('1', (nop,))
    blk2 = AHDL_BLOCK('2', (blk1,))
    blk3 = AHDL_BLOCK('3', (blk2,))
    result = blk3.traverse()
    assert result == [nop]


# ============================================================
# AHDL_NOP
# ============================================================

def test_ahdl_nop_str():
    nop = AHDL_NOP('test info')
    assert str(nop) == "nop('test info')"


# ============================================================
# AHDL_INLINE
# ============================================================

def test_ahdl_inline_str():
    inl = AHDL_INLINE('some verilog code;')
    assert str(inl) == 'some verilog code;'


# ============================================================
# AHDL_MOVE
# ============================================================

def test_ahdl_move_str_reg_dst(hdl):
    dst_sig = make_reg_sig(hdl, 'dst_mv', 8)
    src_sig = make_reg_sig(hdl, 'src_mv', 8)
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_VAR(src_sig, Ctx.LOAD)
    mv = AHDL_MOVE(dst, src)
    assert str(mv) == 'dst_mv <= src_mv'


def test_ahdl_move_str_net_dst(hdl):
    dst_sig = make_net_sig(hdl, 'ndst_mv')
    src_sig = make_reg_sig(hdl, 'nsrc_mv', 8)
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_VAR(src_sig, Ctx.LOAD)
    mv = AHDL_MOVE(dst, src)
    assert str(mv) == 'ndst_mv := nsrc_mv'


def test_ahdl_move_str_const_src(hdl):
    dst_sig = make_reg_sig(hdl, 'dst2_mv', 8)
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_CONST(99)
    mv = AHDL_MOVE(dst, src)
    assert str(mv) == 'dst2_mv <= 99'


def test_ahdl_move_subscript_dst(hdl):
    sig = make_reg_sig(hdl, 'arr_mv', 8)
    mvar = AHDL_MEMVAR(sig, Ctx.STORE)
    sub = AHDL_SUBSCRIPT(mvar, AHDL_CONST(0))
    src = AHDL_CONST(5)
    mv = AHDL_MOVE(sub, src)
    assert str(mv) == 'arr_mv[8][0] <= 5'


def test_ahdl_move_invalid_dst_raises():
    c = AHDL_CONST(1)
    with pytest.raises(AssertionError):
        AHDL_MOVE(c, AHDL_CONST(2))  # type: ignore[arg-type]


def test_ahdl_move_src_var_must_be_load(hdl):
    dst_sig = make_reg_sig(hdl, 'ddd_mv', 8)
    src_sig = make_reg_sig(hdl, 'sss_mv', 8)
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_VAR(src_sig, Ctx.STORE)  # STORE instead of LOAD — must raise
    with pytest.raises(AssertionError):
        AHDL_MOVE(dst, src)


# ============================================================
# AHDL_ASSIGN
# ============================================================

def test_ahdl_assign_str(hdl):
    dst_sig = make_reg_sig(hdl, 'wire_out', 8)
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_CONST(42)
    asgn = AHDL_ASSIGN(dst, src)
    assert str(asgn) == 'wire_out := 42'
    assert asgn.name == 'wire_out'


def test_ahdl_assign_subscript_dst(hdl):
    sig = make_reg_sig(hdl, 'mem2_as', 8)
    mvar = AHDL_MEMVAR(sig, Ctx.STORE)
    sub = AHDL_SUBSCRIPT(mvar, AHDL_CONST(1))
    asgn = AHDL_ASSIGN(sub, AHDL_CONST(7))
    assert str(asgn) == 'mem2_as[8][1] := 7'


def test_ahdl_assign_invalid_dst_raises():
    with pytest.raises(AssertionError):
        AHDL_ASSIGN(AHDL_CONST(0), AHDL_CONST(1))  # type: ignore[arg-type]


# ============================================================
# AHDL_FUNCTION
# ============================================================

def test_ahdl_function_str(hdl):
    sig = make_reg_sig(hdl, 'fn_out', 8)
    output = AHDL_VAR(sig, Ctx.STORE)
    fn = AHDL_FUNCTION(output, (), ())
    assert str(fn) == 'function fn_out'
    assert fn.name == 'fn_out'


# ============================================================
# AHDL_COMB
# ============================================================

def test_ahdl_comb_str():
    comb = AHDL_COMB('my_comb', ())
    assert str(comb) == 'COMB my_comb'


# ============================================================
# AHDL_EVENT_TASK
# ============================================================

def test_ahdl_event_task_str(hdl):
    sig = make_reg_sig(hdl, 'clk', 1)
    nop = AHDL_NOP('body')
    ev = AHDL_EVENT_TASK(((sig, 'posedge'),), nop)
    s = str(ev)
    assert 'posedge' in s
    assert 'clk' in s


# ============================================================
# AHDL_CONNECT
# ============================================================

def test_ahdl_connect_str():
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    conn = AHDL_CONNECT(a, b)
    assert str(conn) == '1 = 2'


# ============================================================
# AHDL_IO_READ
# ============================================================

def test_ahdl_io_read_str_with_dst(hdl):
    io_sig = make_reg_sig(hdl, 'io_port', 8)
    dst_sig = make_reg_sig(hdl, 'dst_io', 8)
    io_var = AHDL_VAR(io_sig, Ctx.LOAD)
    dst_var = AHDL_VAR(dst_sig, Ctx.STORE)
    rd = AHDL_IO_READ(io_var, dst_var, False)
    assert str(rd) == 'dst_io <= io_port.rd()'


def test_ahdl_io_read_str_no_dst(hdl):
    io_sig = make_reg_sig(hdl, 'io_port2', 8)
    io_var = AHDL_VAR(io_sig, Ctx.LOAD)
    rd = AHDL_IO_READ(io_var, None, True)
    assert str(rd) == 'io_port2.rd()'


# ============================================================
# AHDL_IO_WRITE
# ============================================================

def test_ahdl_io_write_str(hdl):
    io_sig = make_reg_sig(hdl, 'io_wr_port', 8)
    io_var = AHDL_VAR(io_sig, Ctx.LOAD)
    wr = AHDL_IO_WRITE(io_var, AHDL_CONST(55), False)
    assert str(wr) == 'io_wr_port.wr(55)'


# ============================================================
# AHDL_SEQ
# ============================================================

def test_ahdl_seq_str():
    nop = AHDL_NOP('seq_body')
    seq = AHDL_SEQ(nop, 2, 5)
    assert str(seq) == "Sequence 2 : nop('seq_body')"


# ============================================================
# AHDL_IF
# ============================================================

def test_ahdl_if_str_if_only():
    cond = AHDL_CONST(1)
    body = AHDL_BLOCK('b', (AHDL_NOP('x'),))
    ahdl_if = AHDL_IF((cond,), (body,))
    s = str(ahdl_if)
    assert s.startswith('if 1')


def test_ahdl_if_str_if_else():
    cond = AHDL_CONST(1)
    body_if = AHDL_BLOCK('if', (AHDL_NOP('if_body'),))
    body_else = AHDL_BLOCK('else', (AHDL_NOP('else_body'),))
    ahdl_if = AHDL_IF((cond, None), (body_if, body_else))
    s = str(ahdl_if)
    assert 'if 1' in s
    assert 'else' in s
    assert 'elif' not in s


def test_ahdl_if_str_if_elif_else():
    cond1 = AHDL_CONST(1)
    cond2 = AHDL_CONST(2)
    b1 = AHDL_BLOCK('b1', (AHDL_NOP('1'),))
    b2 = AHDL_BLOCK('b2', (AHDL_NOP('2'),))
    b3 = AHDL_BLOCK('b3', (AHDL_NOP('3'),))
    ahdl_if = AHDL_IF((cond1, cond2, None), (b1, b2, b3))
    s = str(ahdl_if)
    assert 'if 1' in s
    assert 'elif 2' in s
    assert 'else' in s


def test_ahdl_if_post_init_mismatched_lengths():
    cond = AHDL_CONST(1)
    body = AHDL_BLOCK('b', ())
    with pytest.raises(AssertionError):
        AHDL_IF((cond,), (body, body))


def test_ahdl_if_post_init_first_cond_none_raises():
    body = AHDL_BLOCK('b', ())
    with pytest.raises(AssertionError):
        AHDL_IF((None,), (body,))  # type: ignore[arg-type]


# ============================================================
# AHDL_MODULECALL
# ============================================================

def test_ahdl_modulecall_str():
    mc = AHDL_MODULECALL(None, (AHDL_CONST(1), AHDL_CONST(2)), 'inst0', 'pref_', ())
    assert str(mc) == 'inst0(1, 2)'


def test_ahdl_modulecall_str_no_args():
    mc = AHDL_MODULECALL(None, (), 'inst1', '', ())
    assert str(mc) == 'inst1()'


# ============================================================
# AHDL_PROCCALL
# ============================================================

def test_ahdl_proccall_str():
    pc = AHDL_PROCCALL('my_proc', (AHDL_CONST(10),))
    assert str(pc) == 'my_proc(10)'


def test_ahdl_proccall_str_no_args():
    pc = AHDL_PROCCALL('no_arg_proc', ())
    assert str(pc) == 'no_arg_proc()'


# ============================================================
# AHDL_META_WAIT
# ============================================================

def test_ahdl_meta_wait_str_scalar_args():
    mw = AHDL_META_WAIT('wait_cond', AHDL_CONST(1), AHDL_CONST(2))
    s = str(mw)
    assert s == 'wait_cond(1, 2)'


def test_ahdl_meta_wait_str_list_arg():
    mw = AHDL_META_WAIT('wait_list', [AHDL_CONST(3), AHDL_CONST(4)])
    s = str(mw)
    assert s == 'wait_list(3, 4)'


def test_ahdl_meta_wait_str_tuple_arg():
    mw = AHDL_META_WAIT('wait_tuple', (AHDL_CONST(5), AHDL_CONST(6)))
    s = str(mw)
    assert s == 'wait_tuple(5, 6)'


def test_ahdl_meta_wait_str_mixed_args():
    mw = AHDL_META_WAIT('wait_mix', AHDL_CONST(0), [AHDL_CONST(7), AHDL_CONST(8)])
    s = str(mw)
    assert s == 'wait_mix(0, 7, 8)'


# ============================================================
# AHDL_CASE_ITEM and AHDL_CASE
# ============================================================

def test_ahdl_case_item_str():
    val = AHDL_CONST(3)
    blk = AHDL_BLOCK('b', (AHDL_NOP('ci'),))
    item = AHDL_CASE_ITEM(val, blk)
    s = str(item)
    assert '3:' in s


def test_ahdl_case_str(hdl):
    sig = make_reg_sig(hdl, 'sel', 4)
    sel_var = AHDL_VAR(sig, Ctx.LOAD)
    val1 = AHDL_CONST(0)
    val2 = AHDL_CONST(1)
    b1 = AHDL_BLOCK('b1', (AHDL_NOP('0'),))
    b2 = AHDL_BLOCK('b2', (AHDL_NOP('1'),))
    item1 = AHDL_CASE_ITEM(val1, b1)
    item2 = AHDL_CASE_ITEM(val2, b2)
    case = AHDL_CASE(sel_var, (item1, item2))
    s = str(case)
    assert 'case sel' in s
    assert '0:' in s
    assert '1:' in s


# ============================================================
# AHDL_TRANSITION
# ============================================================

def test_ahdl_transition_str_with_target():
    t = AHDL_TRANSITION('STATE_A')
    assert str(t) == 'goto STATE_A'


def test_ahdl_transition_str_empty_target():
    t = AHDL_TRANSITION('')
    assert str(t) == 'goto None'
    assert t.is_empty() is True


def test_ahdl_transition_is_empty_false():
    t = AHDL_TRANSITION('SOME_STATE')
    assert t.is_empty() is False


def test_ahdl_transition_update_target():
    t = AHDL_TRANSITION('OLD')
    t.update_target('NEW')
    assert t.target_name == 'NEW'


# ============================================================
# State
# ============================================================

def test_state_str():
    nop = AHDL_NOP('s')
    blk = AHDL_BLOCK('b', (nop,))
    state = State('MY_STATE', blk, 0, None)
    s = str(state)
    assert 'MY_STATE' in s
    assert '0' in s


def test_state_traverse():
    nop1 = AHDL_NOP('a')
    nop2 = AHDL_NOP('b')
    inner = AHDL_BLOCK('inner', (nop1,))
    outer = AHDL_BLOCK('outer', (inner, nop2))
    state = State('S', outer, 1, None)
    result = state.traverse()
    assert result == [nop1, nop2]


def test_state_traverse_flat():
    nop = AHDL_NOP('flat')
    blk = AHDL_BLOCK('b', (nop,))
    state = State('FLAT', blk, 2, None)
    result = state.traverse()
    assert result == [nop]


# ============================================================
# AHDL.find_ahdls
# ============================================================

def test_find_ahdls_basic():
    """find_ahdls returns all matching nodes including self."""
    c1 = AHDL_CONST(1)
    c2 = AHDL_CONST(2)
    op = AHDL_OP('Add', c1, c2)
    result = op.find_ahdls(AHDL_CONST)
    assert c1 in result
    assert c2 in result


def test_find_ahdls_nested_block():
    """find_ahdls traverses nested structures inside AHDL_BLOCK."""
    nop1 = AHDL_NOP('a')
    nop2 = AHDL_NOP('b')
    blk = AHDL_BLOCK('b', (nop1, nop2))
    result = blk.find_ahdls(AHDL_NOP)
    assert nop1 in result
    assert nop2 in result


def test_find_ahdls_self_reference_skip():
    """find_ahdls skips self to avoid infinite recursion (line 30)."""
    nop = AHDL_NOP('x')
    blk = AHDL_BLOCK('b', (nop,))
    result = blk.find_ahdls(AHDL_BLOCK)
    # The block itself should appear
    assert blk in result


def test_find_ahdls_in_list_field():
    """find_ahdls traverses list/tuple fields (codes in AHDL_BLOCK)."""
    nop1 = AHDL_NOP('n1')
    nop2 = AHDL_NOP('n2')
    blk = AHDL_BLOCK('b', (nop1, nop2))
    result = blk.find_ahdls(AHDL_NOP)
    assert len(result) == 2


def test_find_ahdls_ahdl_if():
    """find_ahdls finds AHDL_CONST nodes inside AHDL_IF structure."""
    cond = AHDL_CONST(99)
    body = AHDL_BLOCK('b', (AHDL_NOP('y'),))
    ahdl_if = AHDL_IF((cond,), (body,))
    result = ahdl_if.find_ahdls(AHDL_CONST)
    assert cond in result


def test_find_ahdls_no_match():
    """find_ahdls returns empty list when nothing matches."""
    nop = AHDL_NOP('nothing')
    blk = AHDL_BLOCK('b', (nop,))
    result = blk.find_ahdls(AHDL_OP)
    assert result == []


def test_find_ahdls_skip_self_child():
    """Line 30: if v is self, skip to prevent infinite loop.

    We exercise this by placing an AHDL node whose field references
    the same object -- simulate via find_ahdls on AHDL_OP which holds
    args tuple containing AHDL_EXP children (not self).
    The real guard at line 30 fires when `v is self`. We verify
    find_ahdls terminates correctly on nested structures.
    """
    c = AHDL_CONST(0)
    op = AHDL_OP('USub', c)
    result = op.find_ahdls(AHDL_CONST)
    assert c in result


# ============================================================
# AHDL_PIPELINE_GUARD
# ============================================================

def test_ahdl_pipeline_guard_creation():
    cond = AHDL_CONST(1)
    nop = AHDL_NOP('pg')
    pg = AHDL_PIPELINE_GUARD(cond, (nop,))
    assert isinstance(pg, AHDL_PIPELINE_GUARD)
    assert pg.conds[0] is cond


# ============================================================
# AHDL_CALLEE_PROLOG / AHDL_CALLEE_EPILOG
# ============================================================

def test_ahdl_callee_prolog():
    prolog = AHDL_CALLEE_PROLOG('my_func')
    assert prolog.name == 'my_func'


def test_ahdl_callee_epilog():
    epilog = AHDL_CALLEE_EPILOG('my_func')
    assert epilog.name == 'my_func'
