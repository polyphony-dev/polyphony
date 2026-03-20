"""Tests for irhelper.py functions."""
from polyphony.compiler.ir.ir import (
    Ctx, Ir, IrExp, IrStm, IrVariable, IrNameExp,
    Const, Temp, Attr, UnOp, BinOp, RelOp, CondOp,
    Call, SysCall, New, MRef, MStore, Array,
    Move, Expr, CJump, Jump, Ret,
)
from polyphony.compiler.ir.irhelper import (
    qualified_symbols, irexp_type, reduce_relexp, reduce_binop, qsym2var,
    expr2ir, is_mem_read, is_mem_write, bits2int, _get_callee_scope,
    program_order,
)
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test, make_block, MockScope


# ============================================================
# Ir.find_irs tests
# ============================================================

def test_find_irs_simple():
    b = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    temps = b.find_irs(Temp)
    assert len(temps) == 1
    assert temps[0].name == 'x'


def test_find_irs_nested():
    b = BinOp(op='Add',
              left=BinOp(op='Mult', left=Temp(name='a'), right=Temp(name='b')),
              right=Const(value=1))
    temps = b.find_irs(Temp)
    assert len(temps) == 2
    names = {t.name for t in temps}
    assert names == {'a', 'b'}


def test_find_irs_in_call():
    c = Call(name='f', func=Temp(name='f', ctx=Ctx.CALL),
             args=[('', Temp(name='a')), ('', Const(value=1))])
    temps = c.find_irs(Temp)
    assert len(temps) == 2
    names = {t.name for t in temps}
    assert names == {'f', 'a'}


def test_find_irs_in_move():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE),
             src=BinOp(op='Add', left=Temp(name='x'), right=Const(value=2)))
    vars = m.find_irs(IrVariable)
    assert len(vars) == 2
    names = {v.name for v in vars}
    assert names == {'y', 'x'}


def test_find_irs_consts():
    b = BinOp(op='Add', left=Const(value=1), right=Const(value=2))
    consts = b.find_irs(Const)
    assert len(consts) == 2


def test_find_irs_empty():
    c = Const(value=42)
    temps = c.find_irs(Temp)
    assert temps == []


def test_find_irs_mref():
    m = MRef(mem=Temp(name='xs'), offset=Temp(name='i'))
    temps = m.find_irs(Temp)
    assert len(temps) == 2


def test_find_irs_array():
    a = Array(items=[Temp(name='a'), Const(value=1), Temp(name='b')])
    temps = a.find_irs(Temp)
    assert len(temps) == 2


def test_find_irs_attr():
    attr = Attr(name='field', exp=Temp(name='self'), attr='field')
    temps = attr.find_irs(Temp)
    assert len(temps) == 1
    assert temps[0].name == 'self'


# ============================================================
# irhelper.qualified_symbols tests
# ============================================================

def test_qualified_symbols_temp():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(8))

    t = Temp(name='x')
    qsyms = qualified_symbols(t, scope)
    assert len(qsyms) == 1
    assert isinstance(qsyms[0], Symbol)
    assert qsyms[0].name == 'x'


def test_qualified_symbols_attr():
    setup_test()
    X = Scope.create(None, 'X', {'class'}, 0)
    X.add_sym('value', tags=set(), typ=Type.int(8))
    Y = Scope.create(None, 'Y', {'class'}, 0)
    Y.add_sym('x', tags=set(), typ=Type.object(X))

    a = Attr(name='value', exp=Temp(name='x'), attr='value')
    qsyms = qualified_symbols(a, Y)
    assert len(qsyms) == 2
    assert qsyms[0].name == 'x'
    assert qsyms[1].name == 'value'


# ============================================================
# irhelper.reduce_relexp tests
# ============================================================

def test_reduce_relexp_and_true():
    # True AND x => x
    exp = RelOp(op='And', left=Const(value=1), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_relexp_and_false():
    # False AND x => 0
    exp = RelOp(op='And', left=Const(value=0), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 0


def test_reduce_relexp_or_true():
    # True OR x => 1
    exp = RelOp(op='Or', left=Const(value=1), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 1


def test_reduce_relexp_or_false():
    # False OR x => x
    exp = RelOp(op='Or', left=Const(value=0), right=Temp(name='x'))
    result = reduce_relexp(exp)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_relexp_not_const():
    # NOT True => 0
    exp = UnOp(op='Not', exp=Const(value=1))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 0


def test_reduce_relexp_not_const_false():
    # NOT False => 1
    exp = UnOp(op='Not', exp=Const(value=0))
    result = reduce_relexp(exp)
    assert isinstance(result, Const)
    assert result.value == 1


def test_reduce_relexp_passthrough():
    # x AND y => unchanged
    exp = RelOp(op='And', left=Temp(name='x'), right=Temp(name='y'))
    result = reduce_relexp(exp)
    assert isinstance(result, RelOp)


# ============================================================
# irhelper.reduce_binop tests
# ============================================================

def test_reduce_binop_add_zero():
    b = BinOp(op='Add', left=Const(value=0), right=Temp(name='x'))
    result = reduce_binop(b)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_binop_mult_one():
    b = BinOp(op='Mult', left=Temp(name='x'), right=Const(value=1))
    result = reduce_binop(b)
    assert isinstance(result, Temp)
    assert result.name == 'x'


def test_reduce_binop_mult_zero():
    b = BinOp(op='Mult', left=Temp(name='x'), right=Const(value=0))
    result = reduce_binop(b)
    assert isinstance(result, Const)
    assert result.value == 0


def test_reduce_binop_passthrough():
    b = BinOp(op='Add', left=Temp(name='x'), right=Temp(name='y'))
    result = reduce_binop(b)
    assert isinstance(result, BinOp)


# ============================================================
# irhelper.irexp_type tests
# ============================================================

def test_irexp_type_const():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    t = irexp_type(Const(value=42), scope)
    assert t.is_int()


def test_irexp_type_temp():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('x', tags=set(), typ=Type.int(16))
    t = irexp_type(Temp(name='x'), scope)
    assert t.is_int()
    assert t.width == 16


def test_irexp_type_relop():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    t = irexp_type(RelOp(op='Eq', left=Temp(name='x'), right=Const(value=0)), scope)
    assert t.is_bool()


def test_irexp_type_array():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    a = Array(items=[Const(value=1), Const(value=2)], mutable=True)
    t = irexp_type(a, scope)
    assert t.is_list()
    assert t.length == 2


# ============================================================
# Ir.find_vars tests
# ============================================================

def test_find_vars_temp():
    m = Move(dst=Temp(name='x', ctx=Ctx.STORE),
             src=BinOp(op='Add', left=Temp(name='x'), right=Const(value=1)))
    vars = m.find_vars(('x',))
    assert len(vars) == 2
    assert all(v.name == 'x' for v in vars)


def test_find_vars_attr():
    m = Move(dst=Attr(name='field', exp=Temp(name='self'), attr='field', ctx=Ctx.STORE),
             src=Attr(name='field', exp=Temp(name='self'), attr='field'))
    vars = m.find_vars(('self', 'field'))
    assert len(vars) == 2


def test_find_vars_not_found():
    m = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
    vars = m.find_vars(('y',))
    assert len(vars) == 0


def test_find_vars_in_call():
    c = Call(name='f', func=Temp(name='f', ctx=Ctx.CALL),
             args=[('', Temp(name='x')), ('', Temp(name='y'))])
    vars = c.find_vars(('x',))
    assert len(vars) == 1


# ============================================================
# Ir.replace tests (including tuple traversal)
# ============================================================

def test_replace_simple_temp():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE),
             src=BinOp(op='Add', left=Temp(name='x'), right=Const(value=1)))
    m.replace(Temp(name='x'), Temp(name='z'))
    assert m.src.left.name == 'z'


def test_replace_in_syscall_args():
    """SysCall.args is list[tuple[str, IrExp]]. The replace method must
    traverse tuples inside lists to find and replace variables."""
    f = Temp(name='len', ctx=Ctx.CALL)
    sc = SysCall(name='len', func=f, args=[('', Temp(name='d'))])
    m = Move(dst=Temp(name='r', ctx=Ctx.STORE), src=sc)
    m.replace(Temp(name='d'), Temp(name='data0'))
    _, arg = m.src.args[0]
    assert arg.name == 'data0'


def test_replace_in_call_args():
    """Call.args is list[tuple[str, IrExp]]. Same tuple traversal needed."""
    f = Temp(name='func', ctx=Ctx.CALL)
    c = Call(name='func', func=f, args=[('x', Temp(name='a')), ('y', Const(value=1))])
    c.replace(Temp(name='a'), Temp(name='b'))
    _, arg = c.args[0]
    assert arg.name == 'b'


def test_replace_in_nested_call_args():
    """Replace inside nested expression within tuple args."""
    f = Temp(name='f', ctx=Ctx.CALL)
    inner = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    c = Call(name='f', func=f, args=[('', inner)])
    c.replace(Temp(name='x'), Temp(name='y'))
    _, arg = c.args[0]
    assert isinstance(arg, BinOp)
    assert arg.left.name == 'y'


def test_replace_no_match():
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    result = m.replace(Temp(name='z'), Temp(name='w'))
    assert not result
    assert m.src == Const(value=1)


# --- subst (non-mutating replace) ---


def test_subst_simple():
    """subst returns new IR, leaves original unchanged."""
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Temp(name='x'))
    m2 = m.subst(Temp(name='x'), Temp(name='z'))
    # Original unchanged
    assert m.src.name == 'x'
    # New has replacement
    assert m2.src.name == 'z'
    assert m2 is not m


def test_subst_no_match():
    """subst returns same object when nothing matches."""
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=1))
    m2 = m.subst(Temp(name='z'), Temp(name='w'))
    assert m2 is m


def test_subst_call_args():
    """subst replaces inside IrCallable.args (tuple of tuples)."""
    f = Temp(name='func', ctx=Ctx.CALL)
    c = Call(name='func', func=f, args=[('x', Temp(name='a')), ('y', Const(value=1))])
    c2 = c.subst(Temp(name='a'), Temp(name='b'))
    # Original unchanged
    _, orig_arg = c.args[0]
    assert orig_arg.name == 'a'
    # New has replacement
    _, new_arg = c2.args[0]
    assert new_arg.name == 'b'


def test_subst_nested_expr():
    """subst replaces inside nested expressions."""
    f = Temp(name='f', ctx=Ctx.CALL)
    inner = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    c = Call(name='f', func=f, args=[('', inner)])
    c2 = c.subst(Temp(name='x'), Temp(name='y'))
    # Original unchanged
    _, orig_arg = c.args[0]
    assert orig_arg.left.name == 'x'
    # New has replacement
    _, new_arg = c2.args[0]
    assert new_arg.left.name == 'y'


def test_subst_in_move():
    """subst on Move replaces in src (ctx must match for equality)."""
    m = Move(dst=Temp(name='y', ctx=Ctx.STORE),
             src=BinOp(op='Add', left=Temp(name='x'), right=Const(value=1)))
    m2 = m.subst(Temp(name='x'), Temp(name='z'))
    # Original unchanged
    assert m.src.left.name == 'x'
    # New has replacement
    assert m2.src.left.name == 'z'
    assert m2.dst.name == 'y'  # dst unchanged (different ctx)


def test_subst_deep_nested_call_in_move():
    """subst through Move > Call > BinOp (3 levels of Ir nesting)."""
    f = Temp(name='f', ctx=Ctx.CALL)
    deep_arg = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    call = Call(func=f, args=[('a', deep_arg)])
    m = Move(dst=Temp(name='r', ctx=Ctx.STORE), src=call)
    m2 = m.subst(Temp(name='x'), Temp(name='y'))
    # Original unchanged at all levels
    assert m.src.args[0][1].left.name == 'x'
    # New replaced at depth
    assert m2.src.args[0][1].left.name == 'y'
    # Intermediate nodes are new objects
    assert m2 is not m
    assert m2.src is not m.src
    # Unrelated parts are shared
    assert m2.src.args[0][1].right is m.src.args[0][1].right


def test_subst_condop_nested():
    """subst through CondOp > BinOp (deeply nested expressions)."""
    cond = RelOp(op='Lt', left=Temp(name='i'), right=Const(value=10))
    left = BinOp(op='Mult', left=Temp(name='x'), right=Temp(name='x'))
    right = UnOp(op='USub', exp=Temp(name='x'))
    co = CondOp(cond=cond, left=left, right=right)
    m = Move(dst=Temp(name='r', ctx=Ctx.STORE), src=co)
    m2 = m.subst(Temp(name='x'), Temp(name='z'))
    # Original unchanged
    assert m.src.left.left.name == 'x'
    assert m.src.right.exp.name == 'x'
    # All 3 occurrences replaced
    assert m2.src.left.left.name == 'z'
    assert m2.src.left.right.name == 'z'
    assert m2.src.right.exp.name == 'z'
    # Cond untouched (no 'x' with matching ctx)
    assert m2.src.cond.left.name == 'i'


def test_subst_multiple_call_args_with_nested():
    """subst replaces in multiple args, each with nested expressions."""
    f = Temp(name='f', ctx=Ctx.CALL)
    arg0 = BinOp(op='Add', left=Temp(name='a'), right=Temp(name='b'))
    arg1 = BinOp(op='Mult', left=Temp(name='a'), right=Const(value=2))
    call = Call(func=f, args=[('x', arg0), ('y', arg1)])
    call2 = call.subst(Temp(name='a'), Temp(name='c'))
    # Original unchanged
    assert call.args[0][1].left.name == 'a'
    assert call.args[1][1].left.name == 'a'
    # Both args replaced
    assert call2.args[0][1].left.name == 'c'
    assert call2.args[1][1].left.name == 'c'
    # Non-matching parts shared
    assert call2.args[0][1].right is call.args[0][1].right
    assert call2.args[1][1].right is call.args[1][1].right


def test_subst_mref_deep():
    """subst through Move > MRef (memory reference with nested index)."""
    idx = BinOp(op='Add', left=Temp(name='i'), right=Const(value=1))
    mref = MRef(mem=Temp(name='arr'), offset=idx, ctx=Ctx.LOAD)
    m = Move(dst=Temp(name='v', ctx=Ctx.STORE), src=mref)
    m2 = m.subst(Temp(name='i'), Temp(name='j'))
    # Original unchanged
    assert m.src.offset.left.name == 'i'
    # Replaced
    assert m2.src.offset.left.name == 'j'
    assert m2.src.mem.name == 'arr'  # mem untouched


# ============================================================
# irhelper.qsym2var tests
# ============================================================

def test_qsym2var_single():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    sym = scope.add_sym('x', tags=set(), typ=Type.int(8))
    var = qsym2var((sym,), Ctx.LOAD)
    assert isinstance(var, Temp)
    assert var.name == 'x'
    assert var.ctx == Ctx.LOAD


def test_qsym2var_nested():
    setup_test()
    X = Scope.create(None, 'X', {'class'}, 0)
    x_sym = X.add_sym('value', tags=set(), typ=Type.int(8))
    Y = Scope.create(None, 'Y', {'class'}, 0)
    y_sym = Y.add_sym('x', tags=set(), typ=Type.object(X))

    var = qsym2var((y_sym, x_sym), Ctx.STORE)
    assert isinstance(var, Attr)
    assert var.name == 'value'
    assert var.ctx == Ctx.STORE
    assert var.exp.name == 'x'


# ===========================================================
# Additional irhelper tests (from test_irhelper_additions.py)
# ===========================================================

from unittest.mock import MagicMock, PropertyMock
from polyphony.compiler.ir.irhelper import (
    is_port_method_call, has_clkfence, has_exclusive_function,
    eval_unop, eval_binop, eval_relop,
)

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
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=call, block='b1')

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = True
        callee_scope.parent.is_port.return_value = True

        scope = MagicMock()
        scope.find_block.return_value = block
        assert has_exclusive_function(stm, scope, callee_scope) is True

    def test_move_with_port_call_timed(self):
        from polyphony.compiler.ir.irhelper import has_exclusive_function
        func = Attr(name='rd', exp=Temp(name='p'), attr='rd', ctx=Ctx.CALL)
        call = Call(func=func, args=[], kwargs={})
        block = MagicMock()
        block.synth_params = {'scheduling': 'timed'}
        stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=call, block='b1')

        callee_scope = MagicMock()
        callee_scope.is_method.return_value = True
        callee_scope.parent.is_port.return_value = True

        scope = MagicMock()
        scope.find_block.return_value = block
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
        scope = MockScope()
        block = make_block(scope)
        stm1 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
        stm2 = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=2))
        stm1 = block.append_stm(stm1)
        stm2 = block.append_stm(stm2)
        block.order = 5
        # Create a mock scope with find_block
        mock_scope = MagicMock()
        mock_scope.find_block.return_value = block
        assert program_order(stm1, mock_scope) == (5, 0)
        assert program_order(stm2, mock_scope) == (5, 1)


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
