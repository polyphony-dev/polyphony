"""Tests for additional helper functions in ir_helper.py."""
import pytest
from unittest.mock import MagicMock, PropertyMock
from polyphony.compiler.ir.ir import (
    Const, Temp, Attr, Ctx, Call, SysCall, New,
    BinOp, UnOp, RelOp, Move, Expr, Array, MRef,
)


class TestIsPortMethodCall:
    """Tests for is_port_method_call with new IR types."""

    def test_non_call_returns_false(self):
        from polyphony.compiler.ir.ir_helper import is_port_method_call
        temp = Temp(name='x', ctx=Ctx.LOAD)
        scope = MagicMock()
        assert is_port_method_call(temp, scope) is False

    def test_call_to_port_method_returns_true(self):
        from polyphony.compiler.ir.ir_helper import is_port_method_call
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
        from polyphony.compiler.ir.ir_helper import is_port_method_call
        func = Attr(name='foo', exp=Temp(name='obj'), attr='foo', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = True
        callee_scope.parent.is_port.return_value = False

        scope = MagicMock()
        assert is_port_method_call(call, scope, callee_scope) is False

    def test_call_to_non_method_returns_false(self):
        from polyphony.compiler.ir.ir_helper import is_port_method_call
        func = Temp(name='foo', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = False

        scope = MagicMock()
        assert is_port_method_call(call, scope, callee_scope) is False


class TestHasClkfence:
    """Tests for has_clkfence with new IR types."""

    def test_clksleep_syscall(self):
        from polyphony.compiler.ir.ir_helper import has_clkfence
        func = Temp(name='polyphony.timing.clksleep', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is True

    def test_wait_rising_syscall(self):
        from polyphony.compiler.ir.ir_helper import has_clkfence
        func = Temp(name='polyphony.timing.wait_rising', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is True

    def test_wait_falling_syscall(self):
        from polyphony.compiler.ir.ir_helper import has_clkfence
        func = Temp(name='polyphony.timing.wait_falling', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is True

    def test_non_clkfence_syscall(self):
        from polyphony.compiler.ir.ir_helper import has_clkfence
        func = Temp(name='polyphony.io.print', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)
        assert has_clkfence(stm) is False

    def test_non_expr_stm(self):
        from polyphony.compiler.ir.ir_helper import has_clkfence
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
        assert has_clkfence(stm) is False

    def test_expr_with_non_syscall(self):
        from polyphony.compiler.ir.ir_helper import has_clkfence
        func = Temp(name='foo', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})
        stm = Expr(exp=call)
        assert has_clkfence(stm) is False


class TestHasExclusiveFunction:
    """Tests for has_exclusive_function with new IR types."""

    def test_move_with_port_call(self):
        from polyphony.compiler.ir.ir_helper import has_exclusive_function
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
        from polyphony.compiler.ir.ir_helper import has_exclusive_function
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
        from polyphony.compiler.ir.ir_helper import has_exclusive_function
        func = Temp(name='polyphony.timing.clksleep', ctx=Ctx.CALL)
        syscall = SysCall(func=func, args=[], kwargs={})
        stm = Expr(exp=syscall)

        scope = MagicMock()
        assert has_exclusive_function(stm, scope) is True

    def test_non_call_stm(self):
        from polyphony.compiler.ir.ir_helper import has_exclusive_function
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
        scope = MagicMock()
        assert has_exclusive_function(stm, scope) is False


class TestFindMoveSrc:
    """Tests for find_move_src with new IR types."""

    def test_find_matching_move(self):
        from polyphony.compiler.ir.ir_helper import find_move_src
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
        from polyphony.compiler.ir.ir_helper import find_move_src
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
        from polyphony.compiler.ir.ir_helper import find_move_src
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
