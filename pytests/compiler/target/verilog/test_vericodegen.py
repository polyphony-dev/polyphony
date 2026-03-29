"""Comprehensive tests for VerilogCodeGen in vericodegen.py."""
import pytest
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_IF, AHDL_MOVE, AHDL_NOP, AHDL_OP,
    AHDL_PROCCALL, AHDL_SUBSCRIPT, AHDL_TRANSITION_IF, AHDL_VAR, AHDL_MEMVAR,
    AHDL_SYMBOL, AHDL_CONCAT, AHDL_SLICE, AHDL_FUNCALL, AHDL_IF_EXP,
    AHDL_INLINE, AHDL_ASSIGN, AHDL_FUNCTION, AHDL_EVENT_TASK,
    AHDL_CONNECT, AHDL_CASE_ITEM, AHDL_CASE, AHDL_PIPELINE_GUARD,
)
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from polyphony.compiler.target.verilog.vericodegen import VerilogCodeGen
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

_MINIMAL_SCOPE_SRC = """
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
"""

_TB_SCOPE_SRC = """
scope MyTB
tags testbench
"""

_MODULE_SCOPE_SRC = """
scope MyMod
tags class module instantiated
"""

_FUNC_MODULE_SRC = """
scope MyFunc
tags function function_module returnable
return int32
"""


def _build_hdl(src):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        scope = env.scopes[name]
        hdl = HDLModule(scope, scope.base_name, scope.base_name)
        env.append_hdlscope(hdl)
        return hdl
    raise RuntimeError("no scope parsed")


@pytest.fixture
def hdl():
    return _build_hdl(_MINIMAL_SCOPE_SRC)


@pytest.fixture
def gen(hdl):
    return VerilogCodeGen(hdl)


def make_reg_sig(hdl, name, width=8):
    return hdl.gen_sig(name, width, {'reg'})


def make_net_sig(hdl, name, width=8):
    return hdl.gen_sig(name, width, {'net'})


# ============================================================
# emit / tab / set_indent / result
# ============================================================

class TestEmitAndHelpers:
    def test_result_initially_empty(self, gen):
        assert gen.result() == ''

    def test_emit_basic(self, gen):
        gen.emit('hello')
        assert gen.result() == 'hello\n'

    def test_emit_no_newline(self, gen):
        gen.emit('hello', newline=False)
        assert gen.result() == 'hello'

    def test_emit_no_indent(self, gen):
        gen.set_indent(4)
        gen.emit('code', with_indent=False)
        assert gen.result() == 'code\n'

    def test_emit_with_indent(self, gen):
        gen.set_indent(4)
        gen.emit('code')
        assert gen.result() == '    code\n'

    def test_emit_continueus_removes_trailing_newline(self, gen):
        gen.emit('first')
        gen.emit(' second', with_indent=False, continueus=True)
        result = gen.result()
        # The first emit ends with \n, continueus strips it, then appends second
        assert 'first second' in result

    def test_tab_zero_indent(self, gen):
        assert gen.tab() == ''

    def test_tab_with_indent(self, gen):
        gen.set_indent(6)
        assert gen.tab() == '      '

    def test_set_indent_increments(self, gen):
        gen.set_indent(2)
        gen.set_indent(2)
        assert gen.indent == 4

    def test_set_indent_decrements(self, gen):
        gen.set_indent(4)
        gen.set_indent(-2)
        assert gen.indent == 2

    def test_multiple_emits_accumulate(self, gen):
        gen.emit('line1')
        gen.emit('line2')
        assert gen.result() == 'line1\nline2\n'


# ============================================================
# _safe_name
# ============================================================

class TestSafeName:
    def test_normal_name_unchanged(self, gen):
        assert gen._safe_name('my_signal') == 'my_signal'

    def test_verilog_keyword_gets_suffix(self, gen):
        # 'reg' is a Verilog keyword
        assert gen._safe_name('reg') == 'reg_'
        assert gen._safe_name('wire') == 'wire_'
        assert gen._safe_name('input') == 'input_'
        assert gen._safe_name('output') == 'output_'
        assert gen._safe_name('module') == 'module_'

    def test_hash_replaced_by_underscore(self, gen):
        assert gen._safe_name('a#b') == 'a_b'

    def test_numeric_start_gets_prefix(self, gen):
        assert gen._safe_name('1signal') == '_1signal'

    def test_numeric_start_after_hash_replace(self, gen):
        # Not numeric-start so no prefix needed
        assert gen._safe_name('sig#1') == 'sig_1'

    def test_normal_name_with_underscore(self, gen):
        assert gen._safe_name('my_var_2') == 'my_var_2'


# ============================================================
# visit_AHDL_CONST
# ============================================================

class TestVisitConst:
    def test_none_value(self, gen):
        c = AHDL_CONST(None)
        result = gen.visit(c)
        assert result == "'bx"

    def test_bool_true(self, gen):
        c = AHDL_CONST(True)
        result = gen.visit(c)
        assert result == '1'

    def test_bool_false(self, gen):
        c = AHDL_CONST(False)
        result = gen.visit(c)
        assert result == '0'

    def test_integer(self, gen):
        c = AHDL_CONST(42)
        result = gen.visit(c)
        assert result == '42'

    def test_string(self, gen):
        c = AHDL_CONST('hello')
        result = gen.visit(c)
        assert result == '"hello"'


# ============================================================
# visit_AHDL_VAR
# ============================================================

class TestVisitVar:
    def test_normal_name(self, gen, hdl):
        sig = make_reg_sig(hdl, 'my_reg')
        var = AHDL_VAR(sig, Ctx.LOAD)
        assert gen.visit(var) == 'my_reg'

    def test_keyword_name_escaped(self, gen, hdl):
        sig = make_reg_sig(hdl, 'reg')
        var = AHDL_VAR(sig, Ctx.LOAD)
        assert gen.visit(var) == 'reg_'


# ============================================================
# visit_AHDL_MEMVAR
# ============================================================

class TestVisitMemvar:
    def test_normal_name(self, gen, hdl):
        sig = make_reg_sig(hdl, 'my_mem')
        mvar = AHDL_MEMVAR(sig, Ctx.LOAD)
        assert gen.visit(mvar) == 'my_mem'

    def test_keyword_name_escaped(self, gen, hdl):
        sig = make_reg_sig(hdl, 'input')
        mvar = AHDL_MEMVAR(sig, Ctx.LOAD)
        assert gen.visit(mvar) == 'input_'


# ============================================================
# visit_AHDL_SUBSCRIPT
# ============================================================

class TestVisitSubscript:
    def test_basic_subscript(self, gen, hdl):
        sig = make_reg_sig(hdl, 'arr', 8)
        mvar = AHDL_MEMVAR(sig, Ctx.LOAD)
        offset = AHDL_CONST(3)
        sub = AHDL_SUBSCRIPT(mvar, offset)
        assert gen.visit(sub) == 'arr[3]'

    def test_subscript_with_var_offset(self, gen, hdl):
        sig = make_reg_sig(hdl, 'arr2', 8)
        idx_sig = make_reg_sig(hdl, 'idx', 4)
        mvar = AHDL_MEMVAR(sig, Ctx.LOAD)
        offset = AHDL_VAR(idx_sig, Ctx.LOAD)
        sub = AHDL_SUBSCRIPT(mvar, offset)
        assert gen.visit(sub) == 'arr2[idx]'


# ============================================================
# visit_AHDL_SYMBOL
# ============================================================

class TestVisitSymbol:
    def test_normal_symbol(self, gen):
        sym = AHDL_SYMBOL('my_func')
        assert gen.visit(sym) == 'my_func'

    def test_keyword_symbol(self, gen):
        sym = AHDL_SYMBOL('input')
        assert gen.visit(sym) == 'input_'

    def test_non_keyword_symbol(self, gen):
        sym = AHDL_SYMBOL('clk')
        assert gen.visit(sym) == 'clk'


# ============================================================
# visit_AHDL_CONCAT
# ============================================================

class TestVisitConcat:
    def test_no_op_concat(self, gen, hdl):
        sig1 = make_reg_sig(hdl, 'ca', 4)
        sig2 = make_reg_sig(hdl, 'cb', 4)
        a = AHDL_VAR(sig1, Ctx.LOAD)
        b = AHDL_VAR(sig2, Ctx.LOAD)
        concat = AHDL_CONCAT((a, b), None)
        result = gen.visit(concat)
        assert result == '{ca, cb}'

    def test_no_op_concat_single(self, gen, hdl):
        sig = make_reg_sig(hdl, 'cx', 4)
        a = AHDL_VAR(sig, Ctx.LOAD)
        concat = AHDL_CONCAT((a,), None)
        result = gen.visit(concat)
        assert result == '{cx}'


# ============================================================
# visit_AHDL_OP
# ============================================================

class TestVisitOp:
    def test_binary_op(self, gen):
        a = AHDL_CONST(1)
        b = AHDL_CONST(2)
        op = AHDL_OP('Add', a, b)
        result = gen.visit(op)
        assert result == '(1 + 2)'

    def test_unary_op_usub(self, gen):
        a = AHDL_CONST(5)
        op = AHDL_OP('USub', a)
        result = gen.visit(op)
        assert result == '-5'

    def test_unary_op_not(self, gen):
        a = AHDL_CONST(1)
        op = AHDL_OP('Not', a)
        result = gen.visit(op)
        assert result == '!1'

    def test_single_arg_non_unop(self, gen):
        # Single arg that is not a unop: just returns the expression
        a = AHDL_CONST(7)
        # We need an op that is NOT in unop list — use 'Add' with single arg trick
        # AHDL_OP.is_unop() checks for USub/UAdd/Not/Invert
        # Let's use UAdd which IS unop:
        op = AHDL_OP('UAdd', a)
        result = gen.visit(op)
        assert result == '+7'

    def test_multi_args_op(self, gen):
        a = AHDL_CONST(1)
        b = AHDL_CONST(2)
        c = AHDL_CONST(3)
        op = AHDL_OP('BitOr', a, b, c)
        result = gen.visit(op)
        assert result == '(1 | 2 | 3)'

    def test_eq_op(self, gen):
        a = AHDL_CONST(0)
        b = AHDL_CONST(1)
        op = AHDL_OP('Eq', a, b)
        result = gen.visit(op)
        assert result == '(0 == 1)'

    def test_rshift_signed(self, hdl, gen):
        """RShift on signed signal should use >>> (arithmetic shift)."""
        sig = hdl.gen_sig('x_signed', 32, {'reg', 'int'})
        var = AHDL_VAR(sig, Ctx.LOAD)
        shift = AHDL_CONST(2)
        op = AHDL_OP('RShift', var, shift)
        result = gen.visit(op)
        assert '>>>' in result

    def test_rshift_unsigned(self, hdl, gen):
        """RShift on unsigned signal should use >> (logical shift)."""
        sig = hdl.gen_sig('y_unsigned', 32, {'reg'})
        var = AHDL_VAR(sig, Ctx.LOAD)
        shift = AHDL_CONST(2)
        op = AHDL_OP('RShift', var, shift)
        result = gen.visit(op)
        assert '>>>' not in result
        assert '>>' in result


# ============================================================
# visit_AHDL_SLICE
# ============================================================

class TestVisitSlice:
    def test_basic_slice(self, gen, hdl):
        sig = make_reg_sig(hdl, 'sliced', 8)
        var = AHDL_VAR(sig, Ctx.LOAD)
        hi = AHDL_CONST(7)
        lo = AHDL_CONST(0)
        slc = AHDL_SLICE(var, hi, lo)
        result = gen.visit(slc)
        assert result == 'sliced[7:0]'

    def test_slice_partial(self, gen, hdl):
        sig = make_reg_sig(hdl, 'sliced2', 16)
        var = AHDL_VAR(sig, Ctx.LOAD)
        hi = AHDL_CONST(11)
        lo = AHDL_CONST(4)
        slc = AHDL_SLICE(var, hi, lo)
        result = gen.visit(slc)
        assert result == 'sliced2[11:4]'


# ============================================================
# visit_AHDL_NOP
# ============================================================

class TestVisitNop:
    def test_nop_with_string_info(self, gen):
        gen.visit(AHDL_NOP('test comment'))
        assert '/*test comment*/' in gen.result()

    def test_nop_with_ahdl_info(self, gen):
        info = AHDL_CONST(42)
        gen.visit(AHDL_NOP(info))
        assert '/*42*/' in gen.result()

    def test_nop_with_none_info(self, gen):
        gen.visit(AHDL_NOP(None))
        # Nothing emitted when info is falsy
        assert gen.result() == ''

    def test_nop_with_empty_string_info(self, gen):
        gen.visit(AHDL_NOP(''))
        # Empty string is falsy, nothing emitted
        assert gen.result() == ''


# ============================================================
# visit_AHDL_INLINE
# ============================================================

class TestVisitInline:
    def test_inline_emits_code(self, gen):
        gen.visit(AHDL_INLINE('$finish;'))
        assert '$finish;' in gen.result()

    def test_inline_emits_verilog(self, gen):
        gen.visit(AHDL_INLINE('assign x = y;'))
        assert 'assign x = y;' in gen.result()


# ============================================================
# visit_AHDL_MOVE
# ============================================================

class TestVisitMove:
    def test_reg_move(self, gen, hdl):
        dst_sig = make_reg_sig(hdl, 'dst_r', 8)
        src_sig = make_reg_sig(hdl, 'src_r', 8)
        dst = AHDL_VAR(dst_sig, Ctx.STORE)
        src = AHDL_VAR(src_sig, Ctx.LOAD)
        mv = AHDL_MOVE(dst, src)
        gen.visit(mv)
        assert 'dst_r <= src_r;' in gen.result()

    def test_const_src_move(self, gen, hdl):
        dst_sig = make_reg_sig(hdl, 'dst_c', 8)
        dst = AHDL_VAR(dst_sig, Ctx.STORE)
        src = AHDL_CONST(99)
        mv = AHDL_MOVE(dst, src)
        gen.visit(mv)
        assert 'dst_c <= 99;' in gen.result()

    def test_subscript_dst_move(self, gen, hdl):
        arr_sig = make_reg_sig(hdl, 'arr_mv', 8)
        mvar = AHDL_MEMVAR(arr_sig, Ctx.STORE)
        sub = AHDL_SUBSCRIPT(mvar, AHDL_CONST(2))
        src = AHDL_CONST(55)
        mv = AHDL_MOVE(sub, src)
        gen.visit(mv)
        assert 'arr_mv[2] <= 55;' in gen.result()

    def test_net_dst_raises(self, gen, hdl):
        net_sig = make_net_sig(hdl, 'net_dst')
        dst = AHDL_VAR(net_sig, Ctx.STORE)
        src = AHDL_CONST(1)
        mv = AHDL_MOVE.__new__(AHDL_MOVE)
        # Force creation bypassing __post_init__ (net dst should trigger assert False in visit)
        object.__setattr__(mv, 'dst', dst)
        object.__setattr__(mv, 'src', src)
        with pytest.raises(AssertionError):
            gen.visit(mv)

    def test_netarray_dst_raises(self, gen, hdl):
        netarr_sig = hdl.gen_sig('netarr_dst', (8, 4), {'netarray'})
        mvar = AHDL_MEMVAR(netarr_sig, Ctx.STORE)
        sub = AHDL_SUBSCRIPT(mvar, AHDL_CONST(0))
        src = AHDL_CONST(1)
        # Construct AHDL_MOVE bypassing __post_init__ check
        mv = AHDL_MOVE.__new__(AHDL_MOVE)
        object.__setattr__(mv, 'dst', sub)
        object.__setattr__(mv, 'src', src)
        with pytest.raises(AssertionError):
            gen.visit(mv)


# ============================================================
# visit_AHDL_IF
# ============================================================

class TestVisitIf:
    def test_simple_if(self, gen, hdl):
        sig = make_reg_sig(hdl, 'cond_sig', 1)
        cond = AHDL_VAR(sig, Ctx.LOAD)
        body = AHDL_BLOCK('b', (AHDL_NOP('x'),))
        ahdl_if = AHDL_IF((cond,), (body,))
        gen.visit(ahdl_if)
        result = gen.result()
        assert 'if (cond_sig) begin' in result
        assert 'end' in result

    def test_if_else(self, gen, hdl):
        sig = make_reg_sig(hdl, 'cond2', 1)
        cond = AHDL_VAR(sig, Ctx.LOAD)
        body1 = AHDL_BLOCK('b1', (AHDL_NOP('then'),))
        body2 = AHDL_BLOCK('b2', (AHDL_NOP('else'),))
        ahdl_if = AHDL_IF((cond, None), (body1, body2))
        gen.visit(ahdl_if)
        result = gen.result()
        assert 'if (cond2) begin' in result
        assert 'end else begin' in result

    def test_if_elif(self, gen, hdl):
        sig1 = make_reg_sig(hdl, 'c1', 1)
        sig2 = make_reg_sig(hdl, 'c2', 1)
        cond1 = AHDL_VAR(sig1, Ctx.LOAD)
        cond2 = AHDL_VAR(sig2, Ctx.LOAD)
        b1 = AHDL_BLOCK('b1', ())
        b2 = AHDL_BLOCK('b2', ())
        ahdl_if = AHDL_IF((cond1, cond2), (b1, b2))
        gen.visit(ahdl_if)
        result = gen.result()
        assert 'if (c1) begin' in result
        assert 'end else if (c2) begin' in result

    def test_const_1_cond_becomes_else(self, gen, hdl):
        sig = make_reg_sig(hdl, 'cond3', 1)
        cond = AHDL_VAR(sig, Ctx.LOAD)
        const_1 = AHDL_CONST(1)
        b1 = AHDL_BLOCK('b1', ())
        b2 = AHDL_BLOCK('b2', ())
        ahdl_if = AHDL_IF((cond, const_1), (b1, b2))
        gen.visit(ahdl_if)
        result = gen.result()
        # const 1 as second cond should produce "else begin"
        assert 'end else begin' in result

    def test_cond_already_parenthesized(self, gen, hdl):
        # AHDL_OP returns parenthesized expression
        a = AHDL_CONST(0)
        b = AHDL_CONST(1)
        cond = AHDL_OP('Eq', a, b)
        body = AHDL_BLOCK('b', ())
        ahdl_if = AHDL_IF((cond,), (body,))
        gen.visit(ahdl_if)
        result = gen.result()
        # Already starts with '(' so no double-wrapping
        assert 'if (0 == 1) begin' in result


# ============================================================
# visit_AHDL_IF_EXP
# ============================================================

class TestVisitIfExp:
    def test_basic(self, gen):
        cond = AHDL_CONST(1)
        lexp = AHDL_CONST(10)
        rexp = AHDL_CONST(20)
        ie = AHDL_IF_EXP(cond, lexp, rexp)
        result = gen.visit(ie)
        assert result == '(1 ? 10 : 20)'

    def test_with_vars(self, gen, hdl):
        cond_sig = make_reg_sig(hdl, 'sel', 1)
        t_sig = make_reg_sig(hdl, 'tval', 8)
        f_sig = make_reg_sig(hdl, 'fval', 8)
        cond = AHDL_VAR(cond_sig, Ctx.LOAD)
        lexp = AHDL_VAR(t_sig, Ctx.LOAD)
        rexp = AHDL_VAR(f_sig, Ctx.LOAD)
        ie = AHDL_IF_EXP(cond, lexp, rexp)
        result = gen.visit(ie)
        assert result == '(sel ? tval : fval)'


# ============================================================
# visit_AHDL_FUNCALL
# ============================================================

class TestVisitFuncall:
    def test_no_args(self, gen, hdl):
        sig = make_reg_sig(hdl, 'my_func', 8)
        name_sym = AHDL_SYMBOL('my_func')
        fc = AHDL_FUNCALL(name_sym, ())
        result = gen.visit(fc)
        assert result == 'my_func()'

    def test_with_args(self, gen, hdl):
        name_sym = AHDL_SYMBOL('rom_fn')
        args = (AHDL_CONST(1), AHDL_CONST(2))
        fc = AHDL_FUNCALL(name_sym, args)
        result = gen.visit(fc)
        assert result == 'rom_fn(1, 2)'


# ============================================================
# visit_AHDL_PROCCALL
# ============================================================

class TestVisitProccall:
    def test_generic_call(self, gen):
        pc = AHDL_PROCCALL('my_task', (AHDL_CONST(1), AHDL_CONST(2)))
        gen.visit(pc)
        assert 'my_task(1, 2);' in gen.result()

    def test_hdl_print(self, gen):
        pc = AHDL_PROCCALL('!hdl_print', (AHDL_CONST(42),))
        gen.visit(pc)
        result = gen.result()
        assert '$display' in result

    def test_hdl_verilog_display(self, gen):
        pc = AHDL_PROCCALL('!hdl_verilog_display', (AHDL_CONST('"msg"'),))
        gen.visit(pc)
        assert '$display' in gen.result()

    def test_hdl_verilog_write(self, gen):
        pc = AHDL_PROCCALL('!hdl_verilog_write', (AHDL_CONST('"msg"'),))
        gen.visit(pc)
        assert '$write' in gen.result()

    def test_hdl_assert(self, gen, hdl):
        cond_sig = make_reg_sig(hdl, 'assert_cond', 1)
        cond_var = AHDL_VAR(cond_sig, Ctx.LOAD)
        pc = AHDL_PROCCALL('!hdl_assert', (cond_var,))
        # _get_source_text does ahdl2dfgnode[id(ahdl)] — inject a stub so it
        # returns None (lineno < 1 triggers early return).
        class _FakeLoc:
            lineno = 0
            filename = ''
        class _FakeTag:
            loc = _FakeLoc()
        class _FakeNode:
            tag = _FakeTag()
        hdl.ahdl2dfgnode[id(pc)] = (None, _FakeNode())
        gen.visit(pc)
        result = gen.result()
        assert 'if (!' in result
        assert '$display' in result
        assert '$finish' in result

    def test_no_args_generic(self, gen):
        pc = AHDL_PROCCALL('reset_state', ())
        gen.visit(pc)
        assert 'reset_state();' in gen.result()


# ============================================================
# visit_AHDL_ASSIGN
# ============================================================

class TestVisitAssign:
    def test_assign_var_to_const(self, gen, hdl):
        net_sig = make_net_sig(hdl, 'out_net', 8)
        dst = AHDL_VAR(net_sig, Ctx.STORE)
        src = AHDL_CONST(0)
        asgn = AHDL_ASSIGN(dst, src)
        gen.visit(asgn)
        assert 'assign out_net = 0;' in gen.result()

    def test_assign_var_to_var(self, gen, hdl):
        net_sig = make_net_sig(hdl, 'net_a', 8)
        reg_sig = make_reg_sig(hdl, 'reg_a', 8)
        dst = AHDL_VAR(net_sig, Ctx.STORE)
        src = AHDL_VAR(reg_sig, Ctx.LOAD)
        asgn = AHDL_ASSIGN(dst, src)
        gen.visit(asgn)
        assert 'assign net_a = reg_a;' in gen.result()


# ============================================================
# visit_AHDL_EVENT_TASK
# ============================================================

class TestVisitEventTask:
    def test_rising_edge(self, gen, hdl):
        sig = make_reg_sig(hdl, 'clk_ev', 1)
        nop = AHDL_NOP('body')
        ev = AHDL_EVENT_TASK(((sig, 'rising'),), nop)
        gen.visit(ev)
        result = gen.result()
        assert 'always @(posedge clk_ev) begin' in result
        assert 'end' in result

    def test_falling_edge(self, gen, hdl):
        sig = make_reg_sig(hdl, 'clk_f', 1)
        nop = AHDL_NOP('body')
        ev = AHDL_EVENT_TASK(((sig, 'falling'),), nop)
        gen.visit(ev)
        result = gen.result()
        assert 'always @(negedge clk_f) begin' in result

    def test_other_edge(self, gen, hdl):
        sig = make_reg_sig(hdl, 'sig_e', 1)
        nop = AHDL_NOP('body')
        ev = AHDL_EVENT_TASK(((sig, 'other'),), nop)
        gen.visit(ev)
        result = gen.result()
        # No posedge/negedge prefix
        assert 'always @(sig_e) begin' in result

    def test_multiple_events(self, gen, hdl):
        sig1 = make_reg_sig(hdl, 'clk_m', 1)
        sig2 = make_reg_sig(hdl, 'rst_m', 1)
        nop = AHDL_NOP('body')
        ev = AHDL_EVENT_TASK(((sig1, 'rising'), (sig2, 'falling')), nop)
        gen.visit(ev)
        result = gen.result()
        assert 'posedge clk_m' in result
        assert 'negedge rst_m' in result


# ============================================================
# visit_AHDL_CONNECT
# ============================================================

class TestVisitConnect:
    def test_basic_connect(self, gen, hdl):
        sig_d = make_reg_sig(hdl, 'dst_conn', 8)
        sig_s = make_reg_sig(hdl, 'src_conn', 8)
        dst = AHDL_VAR(sig_d, Ctx.STORE)
        src = AHDL_VAR(sig_s, Ctx.LOAD)
        conn = AHDL_CONNECT(dst, src)
        gen.visit(conn)
        assert 'dst_conn = src_conn;' in gen.result()

    def test_connect_const_src(self, gen, hdl):
        sig_d = make_reg_sig(hdl, 'dst_c2', 8)
        dst = AHDL_VAR(sig_d, Ctx.STORE)
        src = AHDL_CONST(7)
        conn = AHDL_CONNECT(dst, src)
        gen.visit(conn)
        assert 'dst_c2 = 7;' in gen.result()


# ============================================================
# visit_AHDL_FUNCTION
# ============================================================

class TestVisitFunction:
    def test_scalar_output(self, gen, hdl):
        out_sig = make_reg_sig(hdl, 'fn_out', 8)
        in_sig = make_reg_sig(hdl, 'fn_in', 4)
        output = AHDL_VAR(out_sig, Ctx.STORE)
        inp = AHDL_VAR(in_sig, Ctx.LOAD)
        fn = AHDL_FUNCTION(output, (inp,), ())
        gen.visit(fn)
        result = gen.result()
        assert 'function [7:0] fn_out (' in result
        assert 'input [3:0] fn_in' in result
        assert 'endfunction' in result

    def test_function_no_inputs(self, gen, hdl):
        out_sig = make_reg_sig(hdl, 'fn2_out', 16)
        output = AHDL_VAR(out_sig, Ctx.STORE)
        fn = AHDL_FUNCTION(output, (), ())
        gen.visit(fn)
        result = gen.result()
        assert 'function [15:0] fn2_out (' in result
        assert 'endfunction' in result

    def test_function_multiple_inputs(self, gen, hdl):
        out_sig = make_reg_sig(hdl, 'fn3_out', 8)
        in1 = make_reg_sig(hdl, 'fn3_a', 4)
        in2 = make_reg_sig(hdl, 'fn3_b', 4)
        output = AHDL_VAR(out_sig, Ctx.STORE)
        fn = AHDL_FUNCTION(output, (AHDL_VAR(in1, Ctx.LOAD), AHDL_VAR(in2, Ctx.LOAD)), ())
        gen.visit(fn)
        result = gen.result()
        assert 'fn3_a,' in result
        assert 'fn3_b' in result

    def test_rom_function(self, gen, hdl):
        # ROM function has tuple width (width, size)
        rom_sig = hdl.gen_sig('rom_out', (8, 16), {'reg', 'rom'})
        output = AHDL_VAR(rom_sig, Ctx.STORE)
        in_sig = make_reg_sig(hdl, 'rom_addr', 4)
        fn = AHDL_FUNCTION(output, (AHDL_VAR(in_sig, Ctx.LOAD),), ())
        gen.visit(fn)
        result = gen.result()
        assert 'function [7:0] rom_out (' in result

    def test_function_with_stms(self, gen, hdl):
        out_sig = make_reg_sig(hdl, 'fn4_out', 8)
        output = AHDL_VAR(out_sig, Ctx.STORE)
        stm = AHDL_INLINE('fn4_out = 0;')
        fn = AHDL_FUNCTION(output, (), (stm,))
        gen.visit(fn)
        result = gen.result()
        assert 'fn4_out = 0;' in result


# ============================================================
# visit_AHDL_CASE / visit_AHDL_CASE_ITEM
# ============================================================

class TestVisitCase:
    def test_case_with_items(self, gen, hdl):
        sel_sig = make_reg_sig(hdl, 'state', 4)
        sel = AHDL_VAR(sel_sig, Ctx.LOAD)
        b1 = AHDL_BLOCK('b1', (AHDL_NOP('s0'),))
        b2 = AHDL_BLOCK('b2', (AHDL_NOP('s1'),))
        item1 = AHDL_CASE_ITEM(AHDL_CONST(0), b1)
        item2 = AHDL_CASE_ITEM(AHDL_CONST(1), b2)
        case = AHDL_CASE(sel, (item1, item2))
        gen.visit(case)
        result = gen.result()
        assert 'case (state)' in result
        assert '0: begin' in result
        assert '1: begin' in result
        assert 'endcase' in result

    def test_case_item_emits_block(self, gen, hdl):
        body = AHDL_BLOCK('b', (AHDL_INLINE('x = 1;'),))
        item = AHDL_CASE_ITEM(AHDL_CONST(5), body)
        gen.visit(item)
        result = gen.result()
        assert '5: begin' in result
        assert 'x = 1;' in result
        assert 'end' in result


# ============================================================
# visit_AHDL_BLOCK
# ============================================================

class TestVisitBlock:
    def test_empty_block(self, gen):
        blk = AHDL_BLOCK('b', ())
        gen.visit(blk)
        assert gen.result() == ''

    def test_block_with_codes(self, gen, hdl):
        sig = make_reg_sig(hdl, 'blk_reg', 8)
        dst = AHDL_VAR(sig, Ctx.STORE)
        src = AHDL_CONST(1)
        mv = AHDL_MOVE(dst, src)
        blk = AHDL_BLOCK('b', (mv,))
        gen.visit(blk)
        assert 'blk_reg <= 1;' in gen.result()

    def test_block_visits_all_codes(self, gen):
        blk = AHDL_BLOCK('b', (
            AHDL_INLINE('code1;'),
            AHDL_INLINE('code2;'),
        ))
        gen.visit(blk)
        result = gen.result()
        assert 'code1;' in result
        assert 'code2;' in result


# ============================================================
# visit_AHDL_TRANSITION_IF and visit_AHDL_PIPELINE_GUARD
# ============================================================

class TestVisitTransitionIfAndPipelineGuard:
    def test_transition_if_delegates_to_ahdl_if(self, gen, hdl):
        sig = make_reg_sig(hdl, 'tr_cond', 1)
        cond = AHDL_VAR(sig, Ctx.LOAD)
        body = AHDL_BLOCK('b', ())
        tif = AHDL_TRANSITION_IF((cond,), (body,))
        gen.visit(tif)
        result = gen.result()
        assert 'if (tr_cond) begin' in result

    def test_pipeline_guard_delegates_to_ahdl_if(self, gen, hdl):
        sig = make_reg_sig(hdl, 'pg_cond', 1)
        cond = AHDL_VAR(sig, Ctx.LOAD)
        codes = (AHDL_NOP('pg'),)
        pg = AHDL_PIPELINE_GUARD(cond, codes)
        gen.visit(pg)
        result = gen.result()
        assert 'if (pg_cond) begin' in result


# ============================================================
# _generate_signal
# ============================================================

class TestGenerateSignal:
    def test_scalar_1bit(self, gen, hdl):
        sig = make_reg_sig(hdl, 'bit1', 1)
        result = gen._generate_signal(sig)
        assert result == 'bit1'

    def test_scalar_multibit(self, gen, hdl):
        sig = make_reg_sig(hdl, 'wide', 8)
        result = gen._generate_signal(sig)
        assert result == '       [7:0] wide'

    def test_scalar_signed(self, gen, hdl):
        sig = hdl.gen_sig('signed_sig', 8, {'reg', 'int'})
        result = gen._generate_signal(sig)
        assert 'signed' in result
        assert '[7:0]' in result

    def test_regarray_1bit_width(self, gen, hdl):
        sig = hdl.gen_sig('ra_1bit', (1, 16), {'regarray'})
        result = gen._generate_signal(sig)
        assert 'ra_1bit[0:16-1]' in result

    def test_regarray_multibit(self, gen, hdl):
        sig = hdl.gen_sig('ra_wide', (8, 4), {'regarray'})
        result = gen._generate_signal(sig)
        assert '[7:0]' in result
        assert 'ra_wide' in result
        assert '[0:4-1]' in result

    def test_regarray_signed(self, gen, hdl):
        sig = hdl.gen_sig('ra_signed', (8, 4), {'regarray', 'int'})
        result = gen._generate_signal(sig)
        assert 'signed' in result

    def test_netarray_1bit(self, gen, hdl):
        sig = hdl.gen_sig('na_1bit', (1, 8), {'netarray'})
        result = gen._generate_signal(sig)
        assert 'na_1bit[0:8-1]' in result

    def test_netarray_multibit(self, gen, hdl):
        sig = hdl.gen_sig('na_wide', (4, 8), {'netarray'})
        result = gen._generate_signal(sig)
        assert '[3:0]' in result
        assert '[0:8-1]' in result


# ============================================================
# _generate_localparams
# ============================================================

class TestGenerateLocalparams:
    def test_empty_constants(self, gen, hdl):
        # No constants added, nothing emitted
        gen._generate_localparams()
        assert gen.result() == ''

    def test_with_constants(self, gen, hdl):
        hdl.add_constant('MY_CONST', 42)
        gen._generate_localparams()
        result = gen.result()
        assert '//localparams' in result
        assert 'localparam MY_CONST = 42;' in result

    def test_multiple_constants_sorted(self, hdl):
        hdl.add_constant('Z_CONST', 100)
        hdl.add_constant('A_CONST', 1)
        gen = VerilogCodeGen(hdl)
        gen._generate_localparams()
        result = gen.result()
        # A_CONST should appear before Z_CONST (sorted by name)
        a_pos = result.find('A_CONST')
        z_pos = result.find('Z_CONST')
        assert a_pos < z_pos


# ============================================================
# _generate_decls
# ============================================================

class TestGenerateDecls:
    def test_empty_decls(self, gen, hdl):
        # No signals or decls
        gen._generate_decls()
        result = gen.result()
        assert '//signals' in result
        assert '//combinations:' in result

    def test_reg_signal_emitted(self, gen, hdl):
        hdl.gen_sig('my_r', 8, {'reg'})
        gen._generate_decls()
        result = gen.result()
        assert 'reg ' in result
        assert 'my_r' in result

    def test_net_signal_emitted(self, gen, hdl):
        hdl.gen_sig('my_n', 8, {'net'})
        gen._generate_decls()
        result = gen.result()
        assert 'wire ' in result
        assert 'my_n' in result

    def test_decls_visited(self, gen, hdl):
        net_sig = make_net_sig(hdl, 'decl_out', 8)
        reg_sig = make_reg_sig(hdl, 'decl_in', 8)
        dst = AHDL_VAR(net_sig, Ctx.STORE)
        src = AHDL_VAR(reg_sig, Ctx.LOAD)
        asgn = AHDL_ASSIGN(dst, src)
        hdl.add_decl(asgn)
        gen._generate_decls()
        result = gen.result()
        assert 'assign decl_out = decl_in;' in result


# ============================================================
# _generate_module_header
# ============================================================

class TestGenerateModuleHeader:
    def test_basic_header(self, gen, hdl):
        gen._generate_module_header()
        result = gen.result()
        assert f'module {hdl.qualified_name}' in result
        assert '(' in result
        assert ');' in result

    def test_module_name_in_header(self):
        hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
        gen = VerilogCodeGen(hdl)
        gen._generate_module_header()
        result = gen.result()
        assert 'module F' in result


# ============================================================
# _generate_io_port
# ============================================================

class TestGenerateIoPort:
    def test_function_module_adds_clk_rst(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        gen = VerilogCodeGen(hdl)
        gen.set_indent(4)  # Simulate being inside module header indentation
        gen._generate_io_port()
        result = gen.result()
        assert 'input wire clk' in result
        assert 'input wire rst' in result

    def test_input_port_wire(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        # Add a wire input
        in_sig = hdl.gen_sig('data_in', 8, {'input', 'net'})
        in_var = AHDL_VAR(in_sig, Ctx.LOAD)
        hdl.add_input(in_var)
        gen = VerilogCodeGen(hdl)
        gen._generate_io_port()
        result = gen.result()
        assert 'input  wire' in result
        assert 'data_in' in result

    def test_input_port_reg(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        in_sig = hdl.gen_sig('reg_in', 8, {'input', 'reg'})
        in_var = AHDL_VAR(in_sig, Ctx.LOAD)
        hdl.add_input(in_var)
        gen = VerilogCodeGen(hdl)
        gen._generate_io_port()
        result = gen.result()
        assert 'input  reg' in result

    def test_input_port_signed(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        in_sig = hdl.gen_sig('sint_in', 8, {'input', 'net', 'int'})
        in_var = AHDL_VAR(in_sig, Ctx.LOAD)
        hdl.add_input(in_var)
        gen = VerilogCodeGen(hdl)
        gen._generate_io_port()
        result = gen.result()
        assert 'signed' in result

    def test_input_port_multibit_width(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        in_sig = hdl.gen_sig('wide_in', 16, {'input', 'net'})
        in_var = AHDL_VAR(in_sig, Ctx.LOAD)
        hdl.add_input(in_var)
        gen = VerilogCodeGen(hdl)
        gen._generate_io_port()
        result = gen.result()
        assert '[15:0]' in result

    def test_output_port_net(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        out_sig = hdl.gen_sig('data_out', 8, {'output', 'net'})
        out_var = AHDL_VAR(out_sig, Ctx.STORE)
        hdl.add_output(out_var)
        gen = VerilogCodeGen(hdl)
        gen._generate_io_port()
        result = gen.result()
        assert 'output wire' in result
        assert 'data_out' in result

    def test_output_port_reg(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        out_sig = hdl.gen_sig('reg_out', 8, {'output', 'reg'})
        out_var = AHDL_VAR(out_sig, Ctx.STORE)
        hdl.add_output(out_var)
        gen = VerilogCodeGen(hdl)
        gen._generate_io_port()
        result = gen.result()
        assert 'output reg' in result

    def test_output_port_initializable(self):
        hdl = _build_hdl(_FUNC_MODULE_SRC)
        out_sig = hdl.gen_sig('init_out', 8, {'output', 'reg', 'initializable'})
        out_sig.init_value = 5
        out_var = AHDL_VAR(out_sig, Ctx.STORE)
        hdl.add_output(out_var)
        gen = VerilogCodeGen(hdl)
        gen._generate_io_port()
        result = gen.result()
        assert '= 5' in result


# ============================================================
# generate() / _generate_module() integration
# ============================================================

class TestGenerate:
    def test_generate_produces_endmodule(self, gen, hdl):
        gen.generate()
        result = gen.result()
        assert 'endmodule' in result

    def test_generate_contains_module_keyword(self, gen, hdl):
        gen.generate()
        result = gen.result()
        assert 'module' in result

    def test_generate_minimal_no_error(self, gen, hdl):
        # Should complete without errors
        gen.generate()
        assert gen.result() != ''

    def test_generate_with_constant(self):
        hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
        hdl.add_constant('MY_PARAM', 7)
        gen = VerilogCodeGen(hdl)
        gen.generate()
        result = gen.result()
        assert 'localparam MY_PARAM = 7;' in result

    def test_generate_with_reg_signal(self):
        hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
        hdl.gen_sig('my_reg_s', 8, {'reg'})
        gen = VerilogCodeGen(hdl)
        gen.generate()
        result = gen.result()
        assert 'reg' in result
        assert 'my_reg_s' in result


# ============================================================
# emit continueus branch: prev_code doesn't end with '\n'
# ============================================================

def test_emit_continueus_no_trailing_newline():
    """emit(continueus=True) when prev code has no trailing newline — no strip."""
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    gen = VerilogCodeGen(hdl)
    gen.emit('first', newline=False)   # no '\n' at end
    gen.emit(' appended', with_indent=False, continueus=True)
    assert 'first appended' in gen.result()


# ============================================================
# visit_AHDL_OP — single arg, non-unop (else branch, lines 272-273)
# ============================================================

def test_visit_op_single_arg_non_unop():
    """Single-arg AHDL_OP with non-unary op just returns the expression."""
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    gen = VerilogCodeGen(hdl)
    a = AHDL_CONST(42)
    op = AHDL_OP('Add', a)   # 'Add' is not a unop
    result = gen.visit(op)
    assert result == '42'


# ============================================================
# visit_AHDL_CONCAT — with op (line 257)
# ============================================================

def test_visit_concat_with_op():
    """AHDL_CONCAT with op joins varlist strings with the HDL operator."""
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    gen = VerilogCodeGen(hdl)
    a = AHDL_CONST(1)
    b = AHDL_CONST(2)
    concat = AHDL_CONCAT((a, b), 'BitOr')
    result = gen.visit(concat)
    assert '|' in result


# ============================================================
# visit_PipelineStage (lines 219-221)
# ============================================================

def test_visit_pipeline_stage():
    """visit_PipelineStage emits stage name and visits block."""
    from polyphony.compiler.ahdl.stg_pipeline import PipelineStage
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    gen = VerilogCodeGen(hdl)
    block = AHDL_BLOCK('', (AHDL_NOP('nop'),))
    stage = PipelineStage('MY_STAGE', block, 0, None)
    gen.visit(stage)
    assert 'MY_STAGE' in gen.result()


# ============================================================
# _generate_module_header with parameters (lines 73-79)
# _generate_parameter_decls int and non-int (lines 91-97)
# ============================================================

def test_generate_module_header_with_parameters():
    """_generate_module_header emits #(...) when parameters dict is non-empty."""
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    # Add non-int param
    p_sig = hdl.gen_sig('DEPTH', 8, {'parameter'})
    hdl.parameters[p_sig] = 16
    gen = VerilogCodeGen(hdl)
    gen._generate_module_header()
    result = gen.result()
    assert '#(' in result
    assert 'DEPTH' in result
    assert 'parameter [7:0] DEPTH = 16' in result


def test_generate_parameter_decls_int_type():
    """_generate_parameter_decls emits 'signed' for int-tagged parameters."""
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    p_sig = hdl.gen_sig('COUNT', 16, {'parameter', 'int'})
    hdl.parameters[p_sig] = 0
    gen = VerilogCodeGen(hdl)
    gen.set_indent(2)
    gen._generate_parameter_decls(hdl.parameters)
    result = gen.result()
    assert 'signed' in result
    assert 'COUNT' in result


# ============================================================
# Module tasks (line 67)
# ============================================================

def test_generate_module_with_task():
    """_generate_module visits tasks added to hdlmodule.tasks."""
    from polyphony.compiler.ahdl.ahdl import AHDL_EVENT_TASK
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    clk_sig = hdl.gen_sig('clk', 1, {'reg'})
    reg_sig = hdl.gen_sig('r2', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(0))
    task = AHDL_EVENT_TASK(((clk_sig, 'rising'),), mv)
    hdl.tasks.append(task)
    gen = VerilogCodeGen(hdl)
    gen.generate()
    assert 'always @' in gen.result()


# ============================================================
# Functions in _generate_decls (line 174)
# ============================================================

def test_generate_decls_with_function():
    """_generate_decls visits AHDL_FUNCTION entries in hdlmodule.functions."""
    hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
    out_sig = hdl.gen_sig('fn_r', 8, {'reg'})
    in_sig = hdl.gen_sig('fn_in_r', 4, {'reg'})
    fn = AHDL_FUNCTION(AHDL_VAR(out_sig, Ctx.STORE), (AHDL_VAR(in_sig, Ctx.LOAD),), ())
    hdl.functions.append(fn)
    gen = VerilogCodeGen(hdl)
    gen.set_indent(2)
    gen._generate_decls()
    assert 'function' in gen.result()
    assert 'endfunction' in gen.result()


# ============================================================
# env.hdl_debug_mode — _generate_net_monitor (lines 148-159)
# ============================================================

def test_generate_net_monitor_hdl_debug_mode():
    """_generate_net_monitor emits $display blocks when hdl_debug_mode is True."""
    env.hdl_debug_mode = True
    try:
        hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
        net_sig = hdl.gen_sig('my_net', 8, {'net'})
        gen = VerilogCodeGen(hdl)
        gen.set_indent(2)
        gen._generate_net_monitor()
        result = gen.result()
        assert 'always @(posedge clk)' in result
        assert '$display' in result
        assert 'my_net' in result
    finally:
        env.hdl_debug_mode = False


def test_generate_net_monitor_onehot_signal():
    """_generate_net_monitor emits %b format for onehot signals."""
    env.hdl_debug_mode = True
    try:
        hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
        hdl.gen_sig('onehot_net', 8, {'net', 'onehot'})
        gen = VerilogCodeGen(hdl)
        gen.set_indent(2)
        gen._generate_net_monitor()
        assert '0b%b' in gen.result()
    finally:
        env.hdl_debug_mode = False


# ============================================================
# env.hdl_debug_mode — visit_AHDL_MOVE (lines 302-303)
# ============================================================

def test_visit_move_hdl_debug_mode():
    """visit_AHDL_MOVE emits $display when hdl_debug_mode is True."""
    env.hdl_debug_mode = True
    try:
        hdl = _build_hdl(_MINIMAL_SCOPE_SRC)
        reg_sig = hdl.gen_sig('dbg_r', 8, {'reg'})
        mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(1))
        gen = VerilogCodeGen(hdl)
        gen.visit(mv)
        result = gen.result()
        assert '$display' in result
        assert 'dbg_r <= 1;' in result
    finally:
        env.hdl_debug_mode = False
