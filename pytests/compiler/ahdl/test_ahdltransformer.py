"""Tests for AHDLTransformer covering all visit_* methods and process flows."""
from polyphony.compiler.ahdl.ahdl import (
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
    AHDL_SUBSCRIPT,
    AHDL_SYMBOL,
    AHDL_TRANSITION,
    AHDL_TRANSITION_IF,
    AHDL_VAR,
    State,
)
from polyphony.compiler.ahdl.ahdltransformer import AHDLTransformer
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from pytests.compiler.base import setup_test


# ============================================================
# Test fixtures / helpers
# ============================================================

def build_scope(src):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


_SIMPLE_SCOPE_SRC = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
'''


def make_hdlmodule(scope):
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def make_signal(hdlscope, name, width: int | tuple[int, int] = 8, tags=None):
    if tags is None:
        tags = {'reg'}
    return hdlscope.gen_sig(name, width, tags)


def make_var(sig, ctx=Ctx.LOAD):
    return AHDL_VAR(sig, ctx)


def make_store_var(sig):
    return AHDL_VAR(sig, Ctx.STORE)


def make_load_var(sig):
    return AHDL_VAR(sig, Ctx.LOAD)


def make_transformer_with_hdlmodule():
    """Return (transformer, hdlmodule) ready for direct visit calls."""
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    t = AHDLTransformer()
    t.hdlmodule = hdl  # needed because visit() accesses hdlmodule.ahdl2dfgnode
    return t, hdl, scope


# ============================================================
# __init__
# ============================================================

def test_init_sets_none_attributes():
    t = AHDLTransformer()
    assert t.current_fsm is None
    assert t.current_stg is None
    assert t.current_state is None


# ============================================================
# visit_AHDL_CONST
# ============================================================

def test_visit_AHDL_CONST_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_CONST(42)
    result = t.visit(node)
    assert result is node
    assert result.value == 42


def test_visit_AHDL_CONST_string():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_CONST("'bz")
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_OP
# ============================================================

def test_visit_AHDL_OP_binary():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_OP('Add', AHDL_CONST(1), AHDL_CONST(2))
    result = t.visit(node)
    assert isinstance(result, AHDL_OP)
    assert result.op == 'Add'
    assert len(result.args) == 2
    assert result.args[0] == AHDL_CONST(1)
    assert result.args[1] == AHDL_CONST(2)


def test_visit_AHDL_OP_unary():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_OP('Not', AHDL_CONST(0))
    result = t.visit(node)
    assert isinstance(result, AHDL_OP)
    assert result.op == 'Not'
    assert len(result.args) == 1


# ============================================================
# visit_AHDL_META_OP
# ============================================================

def test_visit_AHDL_META_OP_with_ahdl_and_non_ahdl_args():
    t, hdl, _ = make_transformer_with_hdlmodule()
    # META_OP args can mix AHDL nodes and non-AHDL values (e.g. strings)
    node = AHDL_META_OP('meta_op', AHDL_CONST(10), 'str_arg')
    result = t.visit(node)
    assert isinstance(result, AHDL_META_OP)
    assert result.op == 'meta_op'
    assert result.args[0] == AHDL_CONST(10)
    assert result.args[1] == 'str_arg'


# ============================================================
# visit_AHDL_VAR
# ============================================================

def test_visit_AHDL_VAR_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    sig = make_signal(hdl, 'v_load', 8, {'reg'})
    node = AHDL_VAR(sig, Ctx.LOAD)
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_MEMVAR
# ============================================================

def test_visit_AHDL_MEMVAR_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    sig = make_signal(hdl, 'mem', (8, 4), {'regarray'})
    node = AHDL_MEMVAR(sig, Ctx.LOAD)
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_SUBSCRIPT
# ============================================================

def test_visit_AHDL_SUBSCRIPT():
    t, hdl, _ = make_transformer_with_hdlmodule()
    sig = make_signal(hdl, 'arr', (8, 4), {'regarray'})
    memvar = AHDL_MEMVAR(sig, Ctx.STORE)
    offset = AHDL_CONST(0)
    node = AHDL_SUBSCRIPT(memvar, offset)
    result = t.visit(node)
    assert isinstance(result, AHDL_SUBSCRIPT)
    assert result.memvar == memvar
    assert result.offset == offset


# ============================================================
# visit_AHDL_SYMBOL
# ============================================================

def test_visit_AHDL_SYMBOL_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_SYMBOL("'bz")
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_CONCAT
# ============================================================

def test_visit_AHDL_CONCAT():
    t, hdl, _ = make_transformer_with_hdlmodule()
    s1 = make_signal(hdl, 'c1', 4, {'net'})
    s2 = make_signal(hdl, 'c2', 4, {'net'})
    v1 = AHDL_VAR(s1, Ctx.LOAD)
    v2 = AHDL_VAR(s2, Ctx.LOAD)
    node = AHDL_CONCAT((v1, v2), None)
    result = t.visit(node)
    assert isinstance(result, AHDL_CONCAT)
    assert result.varlist[0] == v1
    assert result.varlist[1] == v2


# ============================================================
# visit_AHDL_SLICE
# ============================================================

def test_visit_AHDL_SLICE():
    t, hdl, _ = make_transformer_with_hdlmodule()
    sig = make_signal(hdl, 'slicevar', 8, {'reg'})
    var = AHDL_VAR(sig, Ctx.LOAD)
    hi = AHDL_CONST(7)
    lo = AHDL_CONST(0)
    node = AHDL_SLICE(var, hi, lo)
    result = t.visit(node)
    assert isinstance(result, AHDL_SLICE)
    assert result.var == var
    assert result.hi == hi
    assert result.lo == lo


# ============================================================
# visit_AHDL_FUNCALL
# ============================================================

def test_visit_AHDL_FUNCALL():
    t, hdl, _ = make_transformer_with_hdlmodule()
    sig = make_signal(hdl, 'fn', 8, {'net'})
    name_var = AHDL_VAR(sig, Ctx.LOAD)
    arg = AHDL_CONST(5)
    node = AHDL_FUNCALL(name_var, (arg,))
    result = t.visit(node)
    assert isinstance(result, AHDL_FUNCALL)
    assert result.name == name_var
    assert result.args == (arg,)


# ============================================================
# visit_AHDL_IF_EXP
# ============================================================

def test_visit_AHDL_IF_EXP():
    t, hdl, _ = make_transformer_with_hdlmodule()
    cond = AHDL_CONST(1)
    lexp = AHDL_CONST(10)
    rexp = AHDL_CONST(20)
    node = AHDL_IF_EXP(cond, lexp, rexp)
    result = t.visit(node)
    assert isinstance(result, AHDL_IF_EXP)
    assert result.cond == cond
    assert result.lexp == lexp
    assert result.rexp == rexp


# ============================================================
# visit_AHDL_BLOCK
# ============================================================

def test_visit_AHDL_BLOCK_empty():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_BLOCK('blk', ())
    result = t.visit(node)
    assert isinstance(result, AHDL_BLOCK)
    assert result.name == 'blk'
    assert result.codes == ()


def test_visit_AHDL_BLOCK_with_codes():
    t, hdl, _ = make_transformer_with_hdlmodule()
    nop = AHDL_NOP('test')
    node = AHDL_BLOCK('blk', (nop,))
    result = t.visit(node)
    assert isinstance(result, AHDL_BLOCK)
    assert len(result.codes) == 1
    assert result.codes[0] is nop


# ============================================================
# visit_AHDL_NOP
# ============================================================

def test_visit_AHDL_NOP_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_NOP('info')
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_INLINE
# ============================================================

def test_visit_AHDL_INLINE_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_INLINE('assign x = 0;')
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_MOVE
# ============================================================

def test_visit_AHDL_MOVE():
    t, hdl, _ = make_transformer_with_hdlmodule()
    dst_sig = make_signal(hdl, 'dst_reg', 8, {'reg'})
    src_sig = make_signal(hdl, 'src_reg', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_VAR(src_sig, Ctx.LOAD)
    node = AHDL_MOVE(dst, src)
    result = t.visit(node)
    assert isinstance(result, AHDL_MOVE)
    assert result.dst == dst
    assert result.src == src


def test_visit_AHDL_MOVE_with_const_src():
    t, hdl, _ = make_transformer_with_hdlmodule()
    dst_sig = make_signal(hdl, 'dst_c', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_CONST(0)
    node = AHDL_MOVE(dst, src)
    result = t.visit(node)
    assert isinstance(result, AHDL_MOVE)
    assert result.src == src


# ============================================================
# visit_AHDL_ASSIGN
# ============================================================

def test_visit_AHDL_ASSIGN():
    t, hdl, _ = make_transformer_with_hdlmodule()
    dst_sig = make_signal(hdl, 'asgn_dst', 8, {'net'})
    src_sig = make_signal(hdl, 'asgn_src', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_VAR(src_sig, Ctx.LOAD)
    node = AHDL_ASSIGN(dst, src)
    result = t.visit(node)
    assert isinstance(result, AHDL_ASSIGN)
    assert result.dst == dst
    assert result.src == src


# ============================================================
# visit_AHDL_FUNCTION
# ============================================================

def test_visit_AHDL_FUNCTION():
    t, hdl, _ = make_transformer_with_hdlmodule()
    out_sig = make_signal(hdl, 'fn_out', 8, {'net'})
    in_sig = make_signal(hdl, 'fn_in', 8, {'reg'})
    output = AHDL_VAR(out_sig, Ctx.STORE)
    inp = AHDL_VAR(in_sig, Ctx.LOAD)
    nop = AHDL_NOP('fn_body')
    node = AHDL_FUNCTION(output, (inp,), (nop,))
    result = t.visit(node)
    assert isinstance(result, AHDL_FUNCTION)
    assert result.output == output
    assert result.inputs == (inp,)
    assert result.stms == (nop,)


# ============================================================
# visit_AHDL_COMB
# ============================================================

def test_visit_AHDL_COMB():
    t, hdl, _ = make_transformer_with_hdlmodule()
    nop = AHDL_NOP('comb_body')
    node = AHDL_COMB('comb_name', (nop,))
    result = t.visit(node)
    assert isinstance(result, AHDL_COMB)
    assert result.name == 'comb_name'
    assert result.stms == (nop,)


# ============================================================
# visit_AHDL_EVENT_TASK
# ============================================================

def test_visit_AHDL_EVENT_TASK():
    t, hdl, _ = make_transformer_with_hdlmodule()
    clk_sig = make_signal(hdl, 'clk_et', 1, {'net'})
    dst_sig = make_signal(hdl, 'et_dst', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    nop = AHDL_NOP('et_body')
    events = ((clk_sig, 'posedge'),)
    node = AHDL_EVENT_TASK(events, nop)
    result = t.visit(node)
    assert isinstance(result, AHDL_EVENT_TASK)
    assert result.events is events
    assert result.stm is nop


# ============================================================
# visit_AHDL_CONNECT
# ============================================================

def test_visit_AHDL_CONNECT():
    t, hdl, _ = make_transformer_with_hdlmodule()
    s1 = make_signal(hdl, 'conn_a', 8, {'net'})
    s2 = make_signal(hdl, 'conn_b', 8, {'reg'})
    dst = AHDL_VAR(s1, Ctx.STORE)
    src = AHDL_VAR(s2, Ctx.LOAD)
    node = AHDL_CONNECT(dst, src)
    result = t.visit(node)
    assert isinstance(result, AHDL_CONNECT)
    assert result.dst == dst
    assert result.src == src


# ============================================================
# visit_AHDL_IO_READ
# ============================================================

def test_visit_AHDL_IO_READ_with_dst():
    t, hdl, _ = make_transformer_with_hdlmodule()
    io_sig = make_signal(hdl, 'io_r', 8, {'reg'})
    dst_sig = make_signal(hdl, 'io_r_dst', 8, {'reg'})
    io_var = AHDL_VAR(io_sig, Ctx.LOAD)
    dst_var = AHDL_VAR(dst_sig, Ctx.STORE)
    node = AHDL_IO_READ(io_var, dst_var, True)
    result = t.visit(node)
    assert isinstance(result, AHDL_IO_READ)
    assert result.io == io_var
    assert result.dst == dst_var
    assert result.is_self is True


def test_visit_AHDL_IO_READ_without_dst():
    t, hdl, _ = make_transformer_with_hdlmodule()
    io_sig = make_signal(hdl, 'io_r2', 8, {'reg'})
    io_var = AHDL_VAR(io_sig, Ctx.LOAD)
    node = AHDL_IO_READ(io_var, None, False)
    result = t.visit(node)
    assert isinstance(result, AHDL_IO_READ)
    assert result.dst is None
    assert result.is_self is False


# ============================================================
# visit_AHDL_IO_WRITE
# ============================================================

def test_visit_AHDL_IO_WRITE():
    t, hdl, _ = make_transformer_with_hdlmodule()
    io_sig = make_signal(hdl, 'io_w', 8, {'reg'})
    io_var = AHDL_VAR(io_sig, Ctx.LOAD)
    src = AHDL_CONST(7)
    node = AHDL_IO_WRITE(io_var, src, False)
    result = t.visit(node)
    assert isinstance(result, AHDL_IO_WRITE)
    assert result.io == io_var
    assert result.src == src


# ============================================================
# visit_AHDL_SEQ
# ============================================================

def test_visit_AHDL_SEQ():
    t, hdl, _ = make_transformer_with_hdlmodule()
    nop = AHDL_NOP('seq_factor')
    node = AHDL_SEQ(nop, 1, 3)
    result = t.visit(node)
    assert isinstance(result, AHDL_SEQ)
    assert result.factor is nop
    assert result.step == 1
    assert result.step_n == 3


# ============================================================
# visit_AHDL_IF
# ============================================================

def test_visit_AHDL_IF_simple():
    t, hdl, _ = make_transformer_with_hdlmodule()
    cond = AHDL_CONST(1)
    blk = AHDL_BLOCK('', ())
    node = AHDL_IF((cond,), (blk,))
    result = t.visit(node)
    assert isinstance(result, AHDL_IF)
    assert result.conds == (cond,)
    assert result.blocks == (blk,)


def test_visit_AHDL_IF_with_else_none_cond():
    t, hdl, _ = make_transformer_with_hdlmodule()
    cond = AHDL_CONST(1)
    blk_if = AHDL_BLOCK('', ())
    blk_else = AHDL_BLOCK('', ())
    node = AHDL_IF((cond, None), (blk_if, blk_else))
    result = t.visit(node)
    assert isinstance(result, AHDL_IF)
    assert result.conds[0] == cond
    assert result.conds[1] is None
    assert len(result.blocks) == 2


# ============================================================
# visit_AHDL_MODULECALL
# ============================================================

def test_visit_AHDL_MODULECALL():
    t, hdl, scope = make_transformer_with_hdlmodule()
    arg = AHDL_CONST(1)
    node = AHDL_MODULECALL(scope, (arg,), 'inst_name', 'pfx', ())
    result = t.visit(node)
    assert isinstance(result, AHDL_MODULECALL)
    assert result.scope is scope
    assert result.args == (arg,)
    assert result.instance_name == 'inst_name'
    assert result.prefix == 'pfx'


# ============================================================
# visit_AHDL_CALLEE_PROLOG / EPILOG
# ============================================================

def test_visit_AHDL_CALLEE_PROLOG_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_CALLEE_PROLOG('fn')
    result = t.visit(node)
    assert result is node


def test_visit_AHDL_CALLEE_EPILOG_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_CALLEE_EPILOG('fn')
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_PROCCALL
# ============================================================

def test_visit_AHDL_PROCCALL():
    t, hdl, _ = make_transformer_with_hdlmodule()
    arg = AHDL_CONST(3)
    node = AHDL_PROCCALL('myproc', (arg,))
    result = t.visit(node)
    assert isinstance(result, AHDL_PROCCALL)
    assert result.name == 'myproc'
    assert result.args == (arg,)


# ============================================================
# visit_AHDL_META_WAIT
# ============================================================

def test_visit_AHDL_META_WAIT_with_ahdl_arg():
    t, hdl, _ = make_transformer_with_hdlmodule()
    ahdl_arg = AHDL_CONST(5)
    node = AHDL_META_WAIT('wait_id', ahdl_arg)
    result = t.visit(node)
    assert isinstance(result, AHDL_META_WAIT)
    assert result.metaid == 'wait_id'
    assert result.args[0] == ahdl_arg


def test_visit_AHDL_META_WAIT_with_non_ahdl_arg():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_META_WAIT('wait_id', 'non_ahdl_arg')
    result = t.visit(node)
    assert isinstance(result, AHDL_META_WAIT)
    assert result.args[0] == 'non_ahdl_arg'


# ============================================================
# visit_AHDL_CASE_ITEM and visit_AHDL_CASE
# ============================================================

def test_visit_AHDL_CASE_ITEM():
    t, hdl, _ = make_transformer_with_hdlmodule()
    val = AHDL_CONST(2)
    blk = AHDL_BLOCK('', ())
    node = AHDL_CASE_ITEM(val, blk)
    result = t.visit(node)
    assert isinstance(result, AHDL_CASE_ITEM)
    assert result.val == val
    assert result.block == blk


def test_visit_AHDL_CASE():
    t, hdl, _ = make_transformer_with_hdlmodule()
    sel_sig = make_signal(hdl, 'case_sel', 4, {'reg'})
    sel = AHDL_VAR(sel_sig, Ctx.LOAD)
    val = AHDL_CONST(0)
    blk = AHDL_BLOCK('', ())
    item = AHDL_CASE_ITEM(val, blk)
    node = AHDL_CASE(sel, (item,))
    result = t.visit(node)
    assert isinstance(result, AHDL_CASE)
    assert result.sel == sel
    assert len(result.items) == 1
    assert result.items[0] == item


# ============================================================
# visit_AHDL_TRANSITION
# ============================================================

def test_visit_AHDL_TRANSITION_identity():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_TRANSITION('S1')
    result = t.visit(node)
    assert result is node


def test_visit_AHDL_TRANSITION_empty():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_TRANSITION('')
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_AHDL_TRANSITION_IF
# ============================================================

def test_visit_AHDL_TRANSITION_IF():
    t, hdl, _ = make_transformer_with_hdlmodule()
    cond = AHDL_CONST(1)
    blk_true = AHDL_BLOCK('', (AHDL_TRANSITION('S_A'),))
    blk_false = AHDL_BLOCK('', (AHDL_TRANSITION('S_B'),))
    node = AHDL_TRANSITION_IF((cond, None), (blk_true, blk_false))
    result = t.visit(node)
    assert isinstance(result, AHDL_TRANSITION_IF)
    assert result.conds[0] == cond
    assert result.conds[1] is None


# ============================================================
# visit_AHDL_PIPELINE_GUARD
# ============================================================

def test_visit_AHDL_PIPELINE_GUARD():
    t, hdl, _ = make_transformer_with_hdlmodule()
    cond = AHDL_CONST(1)
    nop = AHDL_NOP('guard_body')
    node = AHDL_PIPELINE_GUARD(cond, (nop,))
    result = t.visit(node)
    assert isinstance(result, AHDL_PIPELINE_GUARD)
    assert result.conds[0] == cond
    assert len(result.blocks) == 1


# ============================================================
# visit_State
# ============================================================

def test_visit_State():
    t, hdl, _ = make_transformer_with_hdlmodule()
    stg = STG('test_stg', None, hdl)
    blk = AHDL_BLOCK('S0', (AHDL_NOP('x'),))
    state = State('S0', blk, 0, stg)
    result = t.visit(state)
    assert isinstance(result, State)
    assert result.name == 'S0'
    assert result.step == 0
    assert result.stg is stg
    # current_state is set to the input state before transformation
    assert t.current_state is state


# ============================================================
# find_visitor / visit dispatch
# ============================================================

def test_find_visitor_direct_method():
    t, hdl, _ = make_transformer_with_hdlmodule()
    visitor = t.find_visitor(AHDL_CONST)
    assert visitor is not None
    assert visitor.__name__ == 'visit_AHDL_CONST'


def test_find_visitor_inherited_base():
    """AHDL_MEMVAR has its own visitor; if not, it should walk bases."""
    t, hdl, _ = make_transformer_with_hdlmodule()
    # AHDL_MEMVAR inherits from AHDL_VAR; transformer has visit_AHDL_MEMVAR
    visitor = t.find_visitor(AHDL_MEMVAR)
    assert visitor is not None


def test_visit_dispatches_correctly():
    t, hdl, _ = make_transformer_with_hdlmodule()
    node = AHDL_NOP('dispatch_test')
    result = t.visit(node)
    assert result is node


# ============================================================
# visit_codes
# ============================================================

def test_visit_codes_empty():
    t, hdl, _ = make_transformer_with_hdlmodule()
    result = t.visit_codes(())
    assert result == ()


def test_visit_codes_normal_stm():
    t, hdl, _ = make_transformer_with_hdlmodule()
    nop = AHDL_NOP('n')
    result = t.visit_codes((nop,))
    assert len(result) == 1
    assert result[0] is nop


def test_visit_codes_with_none_returning_transformer():
    """A subclass that returns None for a node should omit it from results."""

    class NopDropper(AHDLTransformer):
        def visit_AHDL_NOP(self, ahdl):
            return None  # drop NOPs

    t = NopDropper()
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    t.hdlmodule = hdl

    nop1 = AHDL_NOP('drop_me')
    nop2 = AHDL_NOP('drop_me_too')
    result = t.visit_codes((nop1, nop2))
    assert result == ()


def test_visit_codes_with_tuple_returning_transformer():
    """A subclass that returns a tuple expands it in-place."""

    class NopExpander(AHDLTransformer):
        def visit_AHDL_NOP(self, ahdl):
            # return two AHDL_NOP as a tuple
            return (AHDL_NOP('expanded_a'), AHDL_NOP('expanded_b'))

    t = NopExpander()
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    t.hdlmodule = hdl

    nop = AHDL_NOP('original')
    result = t.visit_codes((nop,))
    assert len(result) == 2
    assert isinstance(result[0], AHDL_NOP) and result[0].info == 'expanded_a'
    assert isinstance(result[1], AHDL_NOP) and result[1].info == 'expanded_b'


# ============================================================
# process_stg
# ============================================================

def test_process_stg_replaces_states():
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    stg = STG('main_stg', None, hdl)

    nop = AHDL_NOP('state_body')
    blk = AHDL_BLOCK('S0', (nop,))
    state = State('S0', blk, 0, stg)
    stg.add_states([state])

    t = AHDLTransformer()
    t.hdlmodule = hdl
    t.process_stg(stg)

    assert t.current_stg is stg
    assert len(stg.states) == 1
    assert stg.states[0].name == 'S0'


def test_process_stg_expanding_state():
    """Subclass that returns a tuple of States from visit_State."""

    class StateExpander(AHDLTransformer):
        def visit_State(self, state):
            self.current_state = state
            blk_a = AHDL_BLOCK('S0a', ())
            blk_b = AHDL_BLOCK('S0b', ())
            s_a = State('S0a', blk_a, 0, state.stg)
            s_b = State('S0b', blk_b, 1, state.stg)
            return (s_a, s_b)

    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    stg = STG('exp_stg', None, hdl)
    blk = AHDL_BLOCK('S0', ())
    state = State('S0', blk, 0, stg)
    stg.add_states([state])

    t = StateExpander()
    t.hdlmodule = hdl
    t.process_stg(stg)

    assert len(stg.states) == 2
    assert stg.states[0].name == 'S0a'
    assert stg.states[1].name == 'S0b'


# ============================================================
# process_fsm
# ============================================================

def test_process_fsm_with_reset_stm():
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    hdl.add_fsm('main', scope)
    fsm = hdl.fsms['main']

    dst_sig = hdl.gen_sig('fsm_dst', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_CONST(0)
    move = AHDL_MOVE(dst, src)
    fsm.reset_stms = [move]

    stg = STG('fsm_stg', None, hdl)
    blk = AHDL_BLOCK('S_INIT', ())
    state = State('S_INIT', blk, 0, stg)
    stg.add_states([state])
    fsm.stgs = [stg]

    t = AHDLTransformer()
    t.hdlmodule = hdl
    t.process_fsm(fsm)

    assert t.current_fsm is fsm
    assert len(fsm.reset_stms) == 1
    assert isinstance(fsm.reset_stms[0], AHDL_MOVE)


def test_process_fsm_non_move_reset_stm_is_dropped():
    """Only AHDL_MOVE stms survive in reset_stms after process_fsm."""
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    hdl.add_fsm('main2', scope)
    fsm = hdl.fsms['main2']

    # A NOP is not an AHDL_MOVE, so it should be dropped
    nop = AHDL_NOP('reset_nop')
    fsm.reset_stms = [nop]

    stg = STG('fsm_stg2', None, hdl)
    blk = AHDL_BLOCK('S0', ())
    state = State('S0', blk, 0, stg)
    stg.add_states([state])
    fsm.stgs = [stg]

    t = AHDLTransformer()
    t.hdlmodule = hdl
    t.process_fsm(fsm)

    assert fsm.reset_stms == []


# ============================================================
# process — decls path
# ============================================================

def test_process_decls_preserved():
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)

    dst_sig = hdl.gen_sig('proc_dst', 8, {'net'})
    src_sig = hdl.gen_sig('proc_src', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_VAR(src_sig, Ctx.LOAD)
    assign = AHDL_ASSIGN(dst, src)
    hdl.decls = [assign]
    hdl.functions = []
    hdl.tasks = []

    t = AHDLTransformer()
    t.process(hdl)

    assert len(hdl.decls) == 1
    assert isinstance(hdl.decls[0], AHDL_ASSIGN)


def test_process_functions_preserved():
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)

    out_sig = hdl.gen_sig('fn_o', 8, {'net'})
    in_sig = hdl.gen_sig('fn_i', 8, {'reg'})
    output = AHDL_VAR(out_sig, Ctx.STORE)
    inp = AHDL_VAR(in_sig, Ctx.LOAD)
    fn = AHDL_FUNCTION(output, (inp,), ())
    hdl.decls = []
    hdl.functions = [fn]
    hdl.tasks = []

    t = AHDLTransformer()
    t.process(hdl)

    assert len(hdl.functions) == 1
    assert isinstance(hdl.functions[0], AHDL_FUNCTION)


def test_process_edge_detectors_roundtrip():
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    hdl.decls = []
    hdl.functions = []
    hdl.tasks = []

    var_sig = hdl.gen_sig('edge_var', 1, {'reg'})
    var = AHDL_VAR(var_sig, Ctx.LOAD)
    old = AHDL_CONST(0)
    new = AHDL_CONST(1)
    hdl.add_edge_detector(var, old, new)

    t = AHDLTransformer()
    t.process(hdl)

    assert len(hdl.edge_detectors) == 1
    (v, o, n) = next(iter(hdl.edge_detectors))
    assert v == var
    assert o == old
    assert n == new


# ============================================================
# process — FSM path
# ============================================================

def test_process_with_fsm():
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    hdl.decls = []
    hdl.functions = []
    hdl.tasks = []

    hdl.add_fsm('proc_fsm', scope)
    fsm = hdl.fsms['proc_fsm']

    dst_sig = hdl.gen_sig('proc_fsm_reg', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    fsm.reset_stms = [AHDL_MOVE(dst, AHDL_CONST(0))]

    stg = STG('proc_stg', None, hdl)
    blk = AHDL_BLOCK('INIT', ())
    state = State('INIT', blk, 0, stg)
    stg.add_states([state])
    fsm.stgs = [stg]

    t = AHDLTransformer()
    t.process(hdl)

    assert len(hdl.fsms) == 1
    assert len(stg.states) == 1


# ============================================================
# process — tasks path
# ============================================================

def test_process_with_tasks():
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    hdl.decls = []
    hdl.functions = []
    # tasks path requires no fsms
    assert not hdl.fsms

    nop = AHDL_NOP('task_nop')
    hdl.tasks = [nop]

    t = AHDLTransformer()
    t.process(hdl)

    assert len(hdl.tasks) == 1
    assert hdl.tasks[0] is nop


# ============================================================
# Subclass override demonstration
# ============================================================

def test_subclass_can_override_visit_AHDL_CONST():
    """Subclasses can replace visit methods to transform nodes."""

    class DoubleConst(AHDLTransformer):
        def visit_AHDL_CONST(self, ahdl):
            return AHDL_CONST(ahdl.value * 2)

    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    t = DoubleConst()
    t.hdlmodule = hdl

    node = AHDL_CONST(21)
    result = t.visit(node)
    assert isinstance(result, AHDL_CONST)
    assert result.value == 42


def test_subclass_replaces_move_src():
    """Subclass overriding visit_AHDL_CONST transforms nested nodes."""

    class ZeroFill(AHDLTransformer):
        def visit_AHDL_CONST(self, ahdl):
            return AHDL_CONST(0)

    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    t = ZeroFill()
    t.hdlmodule = hdl

    dst_sig = hdl.gen_sig('zf_dst', 8, {'reg'})
    dst = AHDL_VAR(dst_sig, Ctx.STORE)
    node = AHDL_MOVE(dst, AHDL_CONST(99))
    result = t.visit(node)
    assert isinstance(result, AHDL_MOVE)
    assert result.src == AHDL_CONST(0)


# ============================================================
# ahdl2dfgnode mapping in visit
# ============================================================

def test_visit_updates_ahdl2dfgnode():
    """visit() re-maps ahdl2dfgnode entries when a node is transformed."""
    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    t = AHDLTransformer()
    t.hdlmodule = hdl

    original_nop = AHDL_NOP('mapped')
    sentinel = object()
    hdl.ahdl2dfgnode[id(original_nop)] = (original_nop, sentinel)

    result = t.visit(original_nop)
    # For NOP the identity transformer returns the same object
    assert id(result) in hdl.ahdl2dfgnode
    assert hdl.ahdl2dfgnode[id(result)][1] is sentinel


def test_visit_new_node_updates_ahdl2dfgnode():
    """When a transformer creates a new node, ahdl2dfgnode is updated to new id."""

    class ConstReplacer(AHDLTransformer):
        def visit_AHDL_NOP(self, ahdl):
            # Return a NEW nop with different info
            return AHDL_NOP('new_nop')

    scope = build_scope(_SIMPLE_SCOPE_SRC)
    hdl = make_hdlmodule(scope)
    t = ConstReplacer()
    t.hdlmodule = hdl

    old_nop = AHDL_NOP('old_nop')
    sentinel = object()
    hdl.ahdl2dfgnode[id(old_nop)] = (old_nop, sentinel)

    result = t.visit(old_nop)
    assert result.info == 'new_nop'
    assert id(result) in hdl.ahdl2dfgnode
    assert hdl.ahdl2dfgnode[id(result)][1] is sentinel
