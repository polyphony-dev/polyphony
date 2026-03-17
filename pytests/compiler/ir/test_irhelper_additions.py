"""Tests for additional helper functions in irhelper.py."""
import pytest
from unittest.mock import MagicMock, PropertyMock
from polyphony.compiler.ir.ir import (
    Const, Temp, Attr, Ctx, Call, SysCall, New,
    BinOp, UnOp, RelOp, Move, Expr, Array, MRef, MStore,
)
from polyphony.compiler.ir.irhelper import (
    reduce_relexp, reduce_binop, qsym2var, expr2ir, eval_unop, eval_binop,
    eval_relop, irexp_type, is_mem_read, is_mem_write, program_order,
    bits2int, is_port_method_call, _get_callee_scope,
)
from pytests.compiler.base import make_block


class TestIsPortMethodCall:
    """Tests for is_port_method_call with new IR types."""

    def test_non_call_returns_false(self):
        from polyphony.compiler.ir.irhelper import is_port_method_call
        temp = Temp(name='x', ctx=Ctx.LOAD)
        scope = MagicMock()
        assert is_port_method_call(temp, scope) is False

    def test_call_to_port_method_returns_true(self):
        from polyphony.compiler.ir.irhelper import is_port_method_call
        # Build a Call whose callee_scope is a method of a port
        func = Attr(name='rd', exp=Temp(name='p'), attr='rd', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})

        # Mock scope resolution
        callee_scope = MagicMock()
        callee_scope.is_method.return_value = True
        callee_scope.parent.is_port.return_value = True

        scope = MagicMock()
        assert is_port_method_call(call, scope, callee_scope) is True

    def test_call_to_non_port_method_returns_false(self):
        from polyphony.compiler.ir.irhelper import is_port_method_call
        func = Attr(name='foo', exp=Temp(name='obj'), attr='foo', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = True
        callee_scope.parent.is_port.return_value = False

        scope = MagicMock()
        assert is_port_method_call(call, scope, callee_scope) is False

    def test_call_to_non_method_returns_false(self):
        from polyphony.compiler.ir.irhelper import is_port_method_call
        func = Temp(name='foo', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = False

        scope = MagicMock()
        assert is_port_method_call(call, scope, callee_scope) is False


class TestHasClkfence:
    """Tests for has_clkfence with new IR types."""

    def test_clksleep_syscall(self):
        from polyphony.compiler.ir.irhelper import has_clkfence
        func = Temp(name='polyphony.timing.clksleep', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is True

    def test_wait_rising_syscall(self):
        from polyphony.compiler.ir.irhelper import has_clkfence
        func = Temp(name='polyphony.timing.wait_rising', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is True

    def test_wait_falling_syscall(self):
        from polyphony.compiler.ir.irhelper import has_clkfence
        func = Temp(name='polyphony.timing.wait_falling', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is True

    def test_non_clkfence_syscall(self):
        from polyphony.compiler.ir.irhelper import has_clkfence
        func = Temp(name='polyphony.io.print', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is False

    def test_non_expr_stm(self):
        from polyphony.compiler.ir.irhelper import has_clkfence
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
        assert has_clkfence(stm) is False

    def test_expr_with_non_syscall(self):
        from polyphony.compiler.ir.irhelper import has_clkfence
        func = Temp(name='foo', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})
        stm = Expr(exp=call)
        assert has_clkfence(stm) is False


class TestHasExclusiveFunction:
    """Tests for has_exclusive_function with new IR types."""

    def test_move_with_port_call(self):
        from polyphony.compiler.ir.irhelper import has_exclusive_function
        func = Attr(name='rd', exp=Temp(name='p'), attr='rd', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})
        block = MagicMock()
        block.synth_params = {'scheduling': 'pipeline'}
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=call, block=block)

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = True
        callee_scope.parent.is_port.return_value = True

        scope = MagicMock()
        assert has_exclusive_function(stm, scope, callee_scope) is True

    def test_move_with_port_call_timed(self):
        from polyphony.compiler.ir.irhelper import has_exclusive_function
        func = Attr(name='rd', exp=Temp(name='p'), attr='rd', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})
        block = MagicMock()
        block.synth_params = {'scheduling': 'timed'}
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=call, block=block)

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = True
        callee_scope.parent.is_port.return_value = True

        scope = MagicMock()
        assert has_exclusive_function(stm, scope, callee_scope) is False

    def test_expr_with_clkfence(self):
        from polyphony.compiler.ir.irhelper import has_exclusive_function
        func = Temp(name='polyphony.timing.clksleep', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)

        scope = MagicMock()
        assert has_exclusive_function(stm, scope) is True

    def test_non_call_stm(self):
        from polyphony.compiler.ir.irhelper import has_exclusive_function
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
        scope = MagicMock()
        assert has_exclusive_function(stm, scope) is False


class TestFindMoveSrc:
    """Tests for find_move_src with new IR types."""

    def test_find_matching_move(self):
        from polyphony.compiler.ir.irhelper import find_move_src
        # Create a block with stms containing a Move whose dst matches a symbol name
        new_exp = New(func=Temp(name='Port', ctx=Ctx.CALL), args=[], kwargs={})
        dst = Temp(name='p', ctx=Ctx.STORE)
        move_stm = Move(dst=dst, src=new_exp)

        block = MagicMock()
        block.stms = [move_stm]

        scope = MagicMock()
        scope.is_class.return_value = False
        scope.traverse_blocks.return_value = [block]

        sym = MagicMock()
        sym.name = 'p'
        sym.scope = scope

        result = find_move_src(sym, New)
        assert result is new_exp

    def test_no_matching_move(self):
        from polyphony.compiler.ir.irhelper import find_move_src
        block = MagicMock()
        block.stms = [
            Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=42)),
        ]

        scope = MagicMock()
        scope.is_class.return_value = False
        scope.traverse_blocks.return_value = [block]

        sym = MagicMock()
        sym.name = 'p'
        sym.scope = scope

        result = find_move_src(sym, New)
        assert result is None

    def test_class_scope_uses_ctor(self):
        from polyphony.compiler.ir.irhelper import find_move_src
        new_exp = New(func=Temp(name='Port', ctx=Ctx.CALL), args=[], kwargs={})
        move_stm = Move(dst=Temp(name='p', ctx=Ctx.STORE), src=new_exp)

        block = MagicMock()
        block.stms = [move_stm]

        ctor_scope = MagicMock()
        ctor_scope.traverse_blocks.return_value = [block]

        class_scope = MagicMock()
        class_scope.is_class.return_value = True
        class_scope.find_ctor.return_value = ctor_scope

        sym = MagicMock()
        sym.name = 'p'
        sym.scope = class_scope

        result = find_move_src(sym, New)
        assert result is new_exp


# ============================================================
# reduce_relexp – And branch with Not(Const) on left/right
# covers lines 48-49, 51-53, 54-56, 61-68, 74
# ============================================================

class TestReduceRelexpAndBranch:
    """Cover the And branch of reduce_relexp with Not(Const) operands."""

    def test_and_left_not_const_truthy(self):
        """And with left=Not(Const(1)) => Const(0) (line 49: truthy path)."""
        right = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='And',
                    left=UnOp(op='Not', exp=Const(value=1)),
                    right=right)
        result = reduce_relexp(exp)
        assert isinstance(result, Const) and result.value == 0

    def test_and_left_not_const_falsy(self):
        """And with left=Not(Const(0)) => right (line 49: falsy path)."""
        right = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='And',
                    left=UnOp(op='Not', exp=Const(value=0)),
                    right=right)
        result = reduce_relexp(exp)
        assert result == right

    def test_and_right_const_truthy(self):
        """And with right=Const(1) => left (line 50-51)."""
        left = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='And', left=left, right=Const(value=1))
        result = reduce_relexp(exp)
        assert result == left

    def test_and_right_const_falsy(self):
        """And with right=Const(0) => Const(0) (line 51)."""
        left = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='And', left=left, right=Const(value=0))
        result = reduce_relexp(exp)
        assert isinstance(result, Const) and result.value == 0

    def test_and_right_not_const_truthy(self):
        """And with right=Not(Const(1)) => Const(0) (line 53)."""
        left = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='And',
                    left=left,
                    right=UnOp(op='Not', exp=Const(value=1)))
        result = reduce_relexp(exp)
        assert isinstance(result, Const) and result.value == 0

    def test_and_right_not_const_falsy(self):
        """And with right=Not(Const(0)) => left (line 53)."""
        left = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='And',
                    left=left,
                    right=UnOp(op='Not', exp=Const(value=0)))
        result = reduce_relexp(exp)
        assert result == left

    def test_and_both_non_const_changed(self):
        """And with nested reducible sub-expressions => model_copy (lines 54-55)."""
        inner_left = RelOp(op='And', left=Const(value=1), right=Temp(name='a', ctx=Ctx.LOAD))
        inner_right = RelOp(op='And', left=Const(value=1), right=Temp(name='b', ctx=Ctx.LOAD))
        exp = RelOp(op='And', left=inner_left, right=inner_right)
        result = reduce_relexp(exp)
        assert isinstance(result, RelOp) and result.op == 'And'


class TestReduceRelexpOrBranch:
    """Cover the Or branch of reduce_relexp (lines 56-68)."""

    def test_or_left_const_truthy(self):
        """Or with left=Const(1) => Const(1) (line 60)."""
        exp = RelOp(op='Or', left=Const(value=1), right=Temp(name='x', ctx=Ctx.LOAD))
        result = reduce_relexp(exp)
        assert isinstance(result, Const) and result.value == 1

    def test_or_left_const_falsy(self):
        """Or with left=Const(0) => right (line 60)."""
        right = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='Or', left=Const(value=0), right=right)
        result = reduce_relexp(exp)
        assert result == right

    def test_or_left_not_const_truthy(self):
        """Or with left=Not(Const(1)) => right (line 62)."""
        right = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='Or',
                    left=UnOp(op='Not', exp=Const(value=1)),
                    right=right)
        result = reduce_relexp(exp)
        assert result == right

    def test_or_left_not_const_falsy(self):
        """Or with left=Not(Const(0)) => Const(1) (line 62)."""
        exp = RelOp(op='Or',
                    left=UnOp(op='Not', exp=Const(value=0)),
                    right=Temp(name='x', ctx=Ctx.LOAD))
        result = reduce_relexp(exp)
        assert isinstance(result, Const) and result.value == 1

    def test_or_right_const_truthy(self):
        """Or with right=Const(1) => Const(1) (line 64)."""
        exp = RelOp(op='Or', left=Temp(name='x', ctx=Ctx.LOAD), right=Const(value=1))
        result = reduce_relexp(exp)
        assert isinstance(result, Const) and result.value == 1

    def test_or_right_const_falsy(self):
        """Or with right=Const(0) => left (line 64)."""
        left = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='Or', left=left, right=Const(value=0))
        result = reduce_relexp(exp)
        assert result == left

    def test_or_right_not_const_truthy(self):
        """Or with right=Not(Const(1)) => left (line 66)."""
        left = Temp(name='x', ctx=Ctx.LOAD)
        exp = RelOp(op='Or',
                    left=left,
                    right=UnOp(op='Not', exp=Const(value=1)))
        result = reduce_relexp(exp)
        assert result == left

    def test_or_right_not_const_falsy(self):
        """Or with right=Not(Const(0)) => Const(1) (line 66)."""
        exp = RelOp(op='Or',
                    left=Temp(name='x', ctx=Ctx.LOAD),
                    right=UnOp(op='Not', exp=Const(value=0)))
        result = reduce_relexp(exp)
        assert isinstance(result, Const) and result.value == 1

    def test_or_both_changed_model_copy(self):
        """Or with changed sub-expressions => model_copy (lines 67-68)."""
        inner_left = RelOp(op='Or', left=Const(value=0), right=Temp(name='a', ctx=Ctx.LOAD))
        inner_right = RelOp(op='Or', left=Const(value=0), right=Temp(name='b', ctx=Ctx.LOAD))
        exp = RelOp(op='Or', left=inner_left, right=inner_right)
        result = reduce_relexp(exp)
        assert isinstance(result, RelOp) and result.op == 'Or'


class TestReduceRelexpNotBranch:
    """Cover the Not branch of reduce_relexp (line 74)."""

    def test_not_non_const(self):
        """Not with non-const inner => UnOp(Not, ...) (line 74)."""
        inner = Temp(name='x', ctx=Ctx.LOAD)
        exp = UnOp(op='Not', exp=inner)
        result = reduce_relexp(exp)
        assert isinstance(result, UnOp) and result.op == 'Not'


# ============================================================
# qsym2var – multi-segment qualified symbol (line 104)
# ============================================================

class TestQsym2var:
    """Cover qsym2var for multi-segment qualified names."""

    def test_three_segment_qsym(self):
        """qsym2var with 3 segments creates Attr chain (line 104)."""
        s1 = MagicMock(); s1.name = 'obj'
        s2 = MagicMock(); s2.name = 'sub'
        s3 = MagicMock(); s3.name = 'field'
        result = qsym2var((s1, s2, s3), Ctx.LOAD)
        assert isinstance(result, Attr)
        assert result.attr == 'field'
        assert result.ctx == Ctx.LOAD
        # Middle segment
        assert isinstance(result.exp, Attr)
        assert result.exp.attr == 'sub'
        assert result.exp.ctx == Ctx.LOAD


# ============================================================
# expr2ir – various Python literals (lines 116-157)
# ============================================================

class TestExpr2ir:
    """Cover expr2ir for None, int, str, list, tuple."""

    def test_none(self):
        result = expr2ir(None)
        assert isinstance(result, Const) and result.value is None

    def test_int(self):
        result = expr2ir(42)
        assert isinstance(result, Const) and result.value == 42

    def test_str(self):
        result = expr2ir('hello')
        assert isinstance(result, Const) and result.value == 'hello'

    def test_list(self):
        result = expr2ir([1, 2, 3])
        assert isinstance(result, Array)
        assert result.mutable is True
        assert len(result.items) == 3

    def test_tuple(self):
        result = expr2ir((10, 20))
        assert isinstance(result, Array)
        assert result.mutable is False
        assert len(result.items) == 2

    def test_nested_list(self):
        result = expr2ir([[1, 2], [3, 4]])
        assert isinstance(result, Array)
        assert result.mutable is True
        assert isinstance(result.items[0], Array)


# ============================================================
# eval_unop – all branches (lines 163, 165, 167, 171)
# ============================================================

class TestEvalUnop:
    """Cover eval_unop for Invert, Not, UAdd, USub, unknown."""

    def test_invert(self):
        assert eval_unop('Invert', 5) == ~5

    def test_not_truthy(self):
        assert eval_unop('Not', 1) == 0

    def test_not_falsy(self):
        assert eval_unop('Not', 0) == 1

    def test_uadd(self):
        assert eval_unop('UAdd', 7) == 7

    def test_usub(self):
        assert eval_unop('USub', 3) == -3

    def test_unknown(self):
        assert eval_unop('Unknown', 3) is None


# ============================================================
# eval_binop – all branches (lines 182-197)
# ============================================================

class TestEvalBinop:
    """Cover eval_binop for all supported operations."""

    def test_add(self):
        assert eval_binop('Add', 3, 4) == 7

    def test_sub(self):
        assert eval_binop('Sub', 10, 3) == 7

    def test_mult(self):
        assert eval_binop('Mult', 3, 4) == 12

    def test_floordiv(self):
        assert eval_binop('FloorDiv', 7, 2) == 3

    def test_mod(self):
        assert eval_binop('Mod', 7, 3) == 1

    def test_lshift(self):
        assert eval_binop('LShift', 1, 4) == 16

    def test_rshift(self):
        assert eval_binop('RShift', 16, 2) == 4

    def test_bitor(self):
        assert eval_binop('BitOr', 0b1010, 0b0101) == 0b1111

    def test_bitxor(self):
        assert eval_binop('BitXor', 0b1010, 0b1100) == 0b0110

    def test_bitand(self):
        assert eval_binop('BitAnd', 0b1010, 0b1100) == 0b1000

    def test_unknown(self):
        assert eval_binop('Unknown', 1, 2) is None


# ============================================================
# eval_relop – all branches (lines 203, 205, 208-223)
# ============================================================

class TestEvalRelop:
    """Cover eval_relop for all supported operations."""

    def test_eq_true(self):
        assert eval_relop('Eq', 1, 1) == 1

    def test_eq_false(self):
        assert eval_relop('Eq', 1, 2) == 0

    def test_noteq(self):
        assert eval_relop('NotEq', 1, 2) == 1

    def test_lt(self):
        assert eval_relop('Lt', 1, 2) == 1

    def test_lte(self):
        assert eval_relop('LtE', 2, 2) == 1

    def test_gt(self):
        assert eval_relop('Gt', 3, 2) == 1

    def test_gte(self):
        assert eval_relop('GtE', 2, 2) == 1

    def test_is(self):
        obj = object()
        assert eval_relop('Is', obj, obj) == 1

    def test_isnot(self):
        assert eval_relop('IsNot', 1, 2) == 1

    def test_and(self):
        assert eval_relop('And', 1, 2) == 1
        assert eval_relop('And', 0, 2) == 0

    def test_or(self):
        assert eval_relop('Or', 0, 0) == 0
        assert eval_relop('Or', 0, 1) == 1

    def test_unknown(self):
        assert eval_relop('Unknown', 1, 2) is None


# ============================================================
# irexp_type – Array, MRef, BinOp, UnOp, Const branches
# ============================================================

class TestIrexpType:
    """Cover irexp_type for various IrExp types."""

    def _mock_scope_with_sym(self, name, typ):
        sym = MagicMock()
        sym.typ = typ
        scope = MagicMock()
        scope.find_sym.return_value = sym
        return scope

    def test_const(self):
        from polyphony.compiler.ir.types.type import Type
        result = irexp_type(Const(value=42), MagicMock())
        assert result == Type.int()

    def test_relop(self):
        from polyphony.compiler.ir.types.type import Type
        exp = RelOp(op='Eq', left=Const(value=1), right=Const(value=1))
        result = irexp_type(exp, MagicMock())
        assert result == Type.bool()

    def test_unop(self):
        from polyphony.compiler.ir.types.type import Type
        exp = UnOp(op='USub', exp=Const(value=5))
        result = irexp_type(exp, MagicMock())
        assert result == Type.int()

    def test_binop(self):
        from polyphony.compiler.ir.types.type import Type
        exp = BinOp(op='Add', left=Const(value=1), right=Const(value=2))
        result = irexp_type(exp, MagicMock())
        assert result == Type.int()

    def test_mref(self):
        from polyphony.compiler.ir.types.type import Type
        mem = Const(value=0)
        mref = MRef(mem=mem, offset=Const(value=0))
        result = irexp_type(mref, MagicMock())
        assert result == Type.int()

    def test_mutable_array(self):
        from polyphony.compiler.ir.types.type import Type
        arr = Array(items=[Const(value=1), Const(value=2)], mutable=True)
        result = irexp_type(arr, MagicMock())
        assert result == Type.list(Type.int(), 2)

    def test_immutable_array(self):
        from polyphony.compiler.ir.types.type import Type
        arr = Array(items=[Const(value=1)], mutable=False)
        result = irexp_type(arr, MagicMock())
        assert result == Type.tuple(Type.int(), 1)

    def test_empty_array(self):
        from polyphony.compiler.ir.types.type import Type
        arr = Array(items=[], mutable=True)
        result = irexp_type(arr, MagicMock())
        assert result == Type.list(Type.none(), 0)

    def test_array_with_repeat(self):
        from polyphony.compiler.ir.types.type import Type
        arr = Array(items=[Const(value=0)], mutable=True, repeat=Const(value=3))
        result = irexp_type(arr, MagicMock())
        assert result == Type.list(Type.int(), 3)

    def test_array_with_non_const_repeat(self):
        from polyphony.compiler.ir.types.type import Type
        arr = Array(items=[Const(value=0)], mutable=True, repeat=Temp(name='n', ctx=Ctx.LOAD))
        result = irexp_type(arr, MagicMock())
        assert result == Type.list(Type.int(), Type.ANY_LENGTH)


# ============================================================
# _get_callee_scope (lines 270-275)
# ============================================================

class TestGetCalleeScope:
    """Cover _get_callee_scope."""

    def test_get_callee_scope(self):
        from polyphony.compiler.ir.symbol import Symbol
        from polyphony.compiler.ir.types.scopetype import ScopeType

        callee_scope_mock = MagicMock()
        func_t = MagicMock(spec=ScopeType)
        func_t.has_scope.return_value = True
        func_t.scope = callee_scope_mock

        sym = MagicMock(spec=Symbol)
        sym.name = 'foo'
        sym.typ = func_t

        scope = MagicMock()
        scope.find_sym.return_value = sym

        func = Temp(name='foo', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})
        result = _get_callee_scope(call, scope)
        assert result is callee_scope_mock


# ============================================================
# is_port_method_call with callee_scope=None (line 264)
# ============================================================

class TestIsPortMethodCallWithResolve:
    """Cover is_port_method_call when callee_scope is None (line 264)."""

    def test_resolves_callee_scope(self):
        from polyphony.compiler.ir.symbol import Symbol
        from polyphony.compiler.ir.types.scopetype import ScopeType

        parent_mock = MagicMock()
        parent_mock.is_port.return_value = True

        callee_scope_mock = MagicMock()
        callee_scope_mock.is_method.return_value = True
        callee_scope_mock.parent = parent_mock

        func_t = MagicMock(spec=ScopeType)
        func_t.has_scope.return_value = True
        func_t.scope = callee_scope_mock

        sym = MagicMock(spec=Symbol)
        sym.name = 'rd'
        sym.typ = func_t

        scope = MagicMock()
        scope.find_sym.return_value = sym

        func = Temp(name='rd', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})
        assert is_port_method_call(call, scope) is True


# ============================================================
# is_mem_read / is_mem_write (lines 326, 331-332)
# ============================================================

class TestIsMemReadWrite:
    """Cover is_mem_read and is_mem_write."""

    def test_is_mem_read_true(self):
        mref = MRef(mem=Temp(name='arr', ctx=Ctx.LOAD), offset=Const(value=0))
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=mref)
        assert is_mem_read(stm) is True

    def test_is_mem_read_false_non_mref(self):
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
        assert is_mem_read(stm) is False

    def test_is_mem_read_false_non_move(self):
        stm = Expr(exp=Const(value=1))
        assert is_mem_read(stm) is False

    def test_is_mem_write_true(self):
        mstore = MStore(mem=Temp(name='arr', ctx=Ctx.STORE),
                        offset=Const(value=0),
                        exp=Const(value=42))
        stm = Expr(exp=mstore)
        assert is_mem_write(stm) is True

    def test_is_mem_write_false(self):
        stm = Expr(exp=Const(value=1))
        assert is_mem_write(stm) is False


# ============================================================
# program_order (lines 337-338)
# ============================================================

class TestProgramOrder:
    """Cover program_order."""

    def test_program_order(self):
        block = make_block()
        stm1 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
        stm2 = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=2))
        block.append_stm(stm1)
        block.append_stm(stm2)
        block.order = 5
        assert program_order(stm1) == (5, 0)
        assert program_order(stm2) == (5, 1)


# ============================================================
# _try_get_constant (line 349)
# ============================================================

class TestTryGetConstant:
    """Cover _try_get_constant."""

    def test_found(self):
        from polyphony.compiler.ir.irhelper import _try_get_constant
        sym = MagicMock()
        sym.scope.constants = {sym: Const(value=42)}
        result = _try_get_constant((sym,), MagicMock())
        assert isinstance(result, Const) and result.value == 42

    def test_not_found(self):
        from polyphony.compiler.ir.irhelper import _try_get_constant
        sym = MagicMock()
        sym.scope.constants = {}
        result = _try_get_constant((sym,), MagicMock())
        assert result is None


# ============================================================
# bits2int (lines 400-401)
# ============================================================

class TestBits2int:
    """Cover bits2int for positive and negative values."""

    def test_positive(self):
        assert bits2int(0b0101, 4) == 5

    def test_negative(self):
        assert bits2int(0b1111, 4) == -1

    def test_negative_8bit(self):
        assert bits2int(0xFF, 8) == -1

    def test_zero(self):
        assert bits2int(0, 8) == 0

    def test_max_positive_8bit(self):
        assert bits2int(0x7F, 8) == 127

    def test_min_negative_8bit(self):
        assert bits2int(0x80, 8) == -128


# ============================================================
# _try_get_constant_pure (lines 355-379)
# ============================================================

class TestTryGetConstantPure:
    """Cover _try_get_constant_pure with mocked env."""

    def test_global_scope_found(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import _try_get_constant_pure

        sym = MagicMock()
        sym.name = 'x'
        sym.scope.is_global.return_value = True
        sym.scope.is_namespace.return_value = False

        runtime_info = MagicMock()
        runtime_info.global_vars = {'__main__': {'x': 42}}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.runtime_info = runtime_info
            result = _try_get_constant_pure((sym,), MagicMock())
        assert isinstance(result, Const) and result.value == 42

    def test_global_scope_not_found(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import _try_get_constant_pure

        sym = MagicMock()
        sym.name = 'y'
        sym.scope.is_global.return_value = True
        sym.scope.is_namespace.return_value = False

        runtime_info = MagicMock()
        runtime_info.global_vars = {'__main__': {}}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.runtime_info = runtime_info
            result = _try_get_constant_pure((sym,), MagicMock())
        assert result is None

    def test_namespace_scope_found(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import _try_get_constant_pure

        sym = MagicMock()
        sym.name = 'val'
        sym.scope.is_global.return_value = False
        sym.scope.is_namespace.return_value = True
        sym.scope.name = 'mymod'

        runtime_info = MagicMock()
        runtime_info.global_vars = {'mymod': {'val': 99}}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.runtime_info = runtime_info
            result = _try_get_constant_pure((sym,), MagicMock())
        assert isinstance(result, Const) and result.value == 99

    def test_empty_dict_returns_none(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import _try_get_constant_pure

        sym = MagicMock()
        sym.name = 'obj'
        sym.scope.is_global.return_value = True
        sym.scope.is_namespace.return_value = False

        runtime_info = MagicMock()
        runtime_info.global_vars = {'__main__': {'obj': {}}}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.runtime_info = runtime_info
            result = _try_get_constant_pure((sym,), MagicMock())
        assert result is None

    def test_nested_lookup(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import _try_get_constant_pure

        sym1 = MagicMock()
        sym1.name = 'obj'
        sym1.scope.is_global.return_value = True
        sym1.scope.is_namespace.return_value = False

        sym2 = MagicMock()
        sym2.name = 'field'

        runtime_info = MagicMock()
        runtime_info.global_vars = {'__main__': {'obj': {'field': 7}}}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.runtime_info = runtime_info
            result = _try_get_constant_pure((sym1, sym2), MagicMock())
        assert isinstance(result, Const) and result.value == 7

    def test_string_sym_in_qsym(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import _try_get_constant_pure

        sym1 = MagicMock()
        sym1.name = 'obj'
        sym1.scope.is_global.return_value = True
        sym1.scope.is_namespace.return_value = False

        runtime_info = MagicMock()
        runtime_info.global_vars = {'__main__': {'obj': {'attr': 10}}}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.runtime_info = runtime_info
            result = _try_get_constant_pure((sym1, 'attr'), MagicMock())
        assert isinstance(result, Const) and result.value == 10


# ============================================================
# try_get_constant (line 391)
# ============================================================

class TestTryGetConstantDispatch:
    """Cover try_get_constant dispatching to pure vs non-pure."""

    def test_pure_mode(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import try_get_constant

        sym = MagicMock()
        sym.name = 'x'
        sym.scope.is_global.return_value = True
        sym.scope.is_namespace.return_value = False
        sym.scope.constants = {}

        runtime_info = MagicMock()
        runtime_info.global_vars = {'__main__': {'x': 5}}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.config.enable_pure = True
            mock_env.runtime_info = runtime_info
            result = try_get_constant((sym,), MagicMock())
        assert isinstance(result, Const) and result.value == 5

    def test_non_pure_mode(self):
        from unittest.mock import patch
        from polyphony.compiler.ir.irhelper import try_get_constant

        sym = MagicMock()
        sym.scope.constants = {sym: Const(value=77)}

        with patch('polyphony.compiler.common.env.env') as mock_env:
            mock_env.config.enable_pure = False
            result = try_get_constant((sym,), MagicMock())
        assert isinstance(result, Const) and result.value == 77
