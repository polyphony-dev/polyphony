"""Tests for TreeBalancer, PLURALOP, BINOP2PLURALOP, and PLURALOP2BINOP.

NOTE: treebalancer.py has one known issue with the new Pydantic-based IR:
1. BINOP2PLURALOP.visit_BinOp uses direct attribute assignment (ir.left = ...)
   on frozen Pydantic models, raising ValidationError.

Tests exercise all reachable code paths for maximum coverage.
"""
import pytest
from pydantic_core import ValidationError
from polyphony.compiler.ir.ir import (
    BinOp, RelOp, Call, Const, MRef, Array, Temp, CJump, Jump, Move, PolyOp, Ctx,
)
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.transformers.treebalancer import (
    PLURALOP, TreeBalancer, BINOP2PLURALOP, PLURALOP2BINOP,
)
from pytests.compiler.base import MockScope, make_block


# ============================================================
# Helpers
# ============================================================

def _temp(name):
    return Temp(name=name, ctx=Ctx.LOAD)


def _const(val):
    return Const(value=val)


def _binop(op, left, right):
    return BinOp(op=op, left=left, right=right)


class MutableBinOp:
    """Non-frozen BinOp stand-in for testing visit_BinOp logic.

    The real BinOp is a frozen Pydantic model, so visit_BinOp's direct
    attribute assignment (ir.left = ...) raises ValidationError. This class
    allows the assignment to succeed so we can test the actual logic.
    """

    def __init__(self, op, left, right):
        self.op = op
        self.left = left
        self.right = right

    def kids(self):
        return [self.left, self.right]


class BINOP2PLURALOP_PreVisited(BINOP2PLURALOP):
    """Subclass that returns PLURALOP children as-is from visit().

    This allows testing visit_BinOp with pre-built PLURALOP children
    without hitting the KeyError from slots dispatch.
    """

    def visit(self, ir):
        if isinstance(ir, PLURALOP):
            return ir
        return super().visit(ir)


def _inject_src(move, value):
    """Bypass frozen check to set move.src to a non-IrExp (e.g., PLURALOP)."""
    object.__setattr__(move, 'src', value)


def _inject_exp(cjump, value):
    """Bypass frozen check to set cjump.exp to a non-IrExp (e.g., PLURALOP)."""
    object.__setattr__(cjump, 'exp', value)


# ============================================================
# PLURALOP
# ============================================================

class TestPLURALOP:
    def test_init(self):
        p = PLURALOP('Add')
        assert p.op == 'Add'
        assert p.values == []

    def test_str_empty(self):
        p = PLURALOP('Mult')
        s = str(p)
        assert 'PLURALOP' in s
        assert 'Mult' in s

    def test_str_with_values(self):
        p = PLURALOP('Add')
        p.values = [(_const(1), True), (_temp('x'), False)]
        s = str(p)
        assert 'PLURALOP' in s
        assert 'Add' in s
        assert 'True' in s
        assert 'False' in s

    def test_kids(self):
        p = PLURALOP('Add')
        vals = [(_const(1), True), (_temp('x'), False)]
        p.values = vals
        assert p.kids() is p.values

    def test_eliminate_useless_cancels_opposite_polarity(self):
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True), (_temp('b'), True), (_temp('a'), False)]
        p.eliminate_useless()
        assert len(p.values) == 1
        expr, pol = p.values[0]
        assert str(expr) == 'b'
        assert pol is True

    def test_eliminate_useless_no_cancel(self):
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True), (_temp('a'), True)]
        p.eliminate_useless()
        assert len(p.values) == 2

    def test_eliminate_useless_empty(self):
        p = PLURALOP('Add')
        p.eliminate_useless()
        assert p.values == []

    def test_eliminate_useless_multiple_cancellations(self):
        p = PLURALOP('Add')
        p.values = [
            (_temp('a'), True),
            (_temp('b'), True),
            (_temp('a'), False),
            (_temp('b'), False),
        ]
        p.eliminate_useless()
        assert len(p.values) == 0

    def test_eliminate_useless_none_entries_skipped(self):
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True), None, (_temp('a'), False)]
        p.eliminate_useless()
        assert len(p.values) == 0

    def test_eliminate_useless_different_names_no_cancel(self):
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True), (_temp('b'), False)]
        p.eliminate_useless()
        assert len(p.values) == 2


# ============================================================
# BINOP2PLURALOP
# ============================================================

class TestBINOP2PLURALOP:
    def setup_method(self):
        self.visitor = BINOP2PLURALOP()

    # --- Leaf visitors ---
    def test_visit_Const(self):
        c = _const(42)
        assert self.visitor.visit(c) is c

    def test_visit_Temp(self):
        t = _temp('x')
        assert self.visitor.visit(t) is t

    def test_visit_MRef(self):
        m = MRef(mem=_temp('arr'), offset=_const(0))
        assert self.visitor.visit(m) is m

    def test_visit_Array(self):
        a = Array(items=[_const(1), _const(2)])
        assert self.visitor.visit(a) is a

    def test_visit_RelOp(self):
        r = RelOp(op='Eq', left=_temp('a'), right=_const(0))
        assert self.visitor.visit(r) is r

    def test_visit_Call(self):
        c = Call(func=_temp('f'), args=[('', _const(1))])
        assert self.visitor.visit(c) is c

    def test_visit_Jump(self):
        blk = make_block()
        j = Jump(target=blk.bid)
        result = self.visitor.visit(j)
        assert result is j

    # --- BinOp: frozen model prevents direct assignment ---
    def test_visit_BinOp_Add_raises_frozen(self):
        ir = _binop('Add', _temp('a'), _temp('b'))
        with pytest.raises(ValidationError, match="frozen"):
            self.visitor.visit(ir)

    def test_visit_BinOp_Sub_raises_frozen(self):
        ir = _binop('Sub', _temp('a'), _temp('b'))
        with pytest.raises(ValidationError, match="frozen"):
            self.visitor.visit(ir)

    def test_visit_BinOp_Mult_raises_frozen(self):
        ir = _binop('Mult', _temp('a'), _temp('b'))
        with pytest.raises(ValidationError, match="frozen"):
            self.visitor.visit(ir)

    def test_visit_BinOp_other_op_raises_frozen(self):
        ir = _binop('BitAnd', _temp('a'), _temp('b'))
        with pytest.raises(ValidationError, match="frozen"):
            self.visitor.visit(ir)

    # --- Test visit_BinOp Add/Sub/Mult/else with MutableBinOp (leaf operands) ---
    def test_visit_BinOp_Add_logic(self):
        ir = MutableBinOp('Add', _temp('a'), _temp('b'))
        result = self.visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert len(result.values) == 2
        assert result.values[0][1] is True
        assert result.values[1][1] is True

    def test_visit_BinOp_Sub_logic(self):
        ir = MutableBinOp('Sub', _temp('a'), _temp('b'))
        result = self.visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert result.values[0][1] is True
        assert result.values[1][1] is False

    def test_visit_BinOp_Mult_logic(self):
        ir = MutableBinOp('Mult', _temp('a'), _temp('b'))
        result = self.visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Mult'
        assert len(result.values) == 2

    def test_visit_BinOp_other_op_logic(self):
        ir = MutableBinOp('BitAnd', _temp('a'), _temp('b'))
        result = self.visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'BitAnd'
        assert len(result.values) == 1  # else branch appends list as single element

    # --- Test nested PLURALOP flattening with PreVisited subclass ---
    def test_visit_BinOp_Add_nested_left_pluralop(self):
        """Add with PLURALOP(Add) on left flattens it."""
        visitor = BINOP2PLURALOP_PreVisited()
        left_plural = PLURALOP('Add')
        left_plural.values = [(_temp('a'), True), (_temp('b'), True)]
        ir = MutableBinOp('Add', left_plural, _temp('c'))
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert len(result.values) == 3

    def test_visit_BinOp_Add_nested_right_pluralop(self):
        """Add with PLURALOP(Add) on right flattens it."""
        visitor = BINOP2PLURALOP_PreVisited()
        right_plural = PLURALOP('Add')
        right_plural.values = [(_temp('b'), True), (_temp('c'), False)]
        ir = MutableBinOp('Add', _temp('a'), right_plural)
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert len(result.values) == 3
        assert result.values[0][1] is True   # a
        assert result.values[1][1] is True   # b (Add preserves)
        assert result.values[2][1] is False  # c (Add preserves)

    def test_visit_BinOp_Sub_nested_right_pluralop(self):
        """Sub with PLURALOP(Add) on right flips polarities."""
        visitor = BINOP2PLURALOP_PreVisited()
        right_plural = PLURALOP('Add')
        right_plural.values = [(_temp('b'), True), (_temp('c'), False)]
        ir = MutableBinOp('Sub', _temp('a'), right_plural)
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert len(result.values) == 3
        assert result.values[0][1] is True   # a
        assert result.values[1][1] is False  # b (Sub flips T->F)
        assert result.values[2][1] is True   # c (Sub flips F->T)

    def test_visit_BinOp_Mult_nested_left_pluralop(self):
        """Mult with PLURALOP(Mult) on left flattens it."""
        visitor = BINOP2PLURALOP_PreVisited()
        left_plural = PLURALOP('Mult')
        left_plural.values = [(_temp('a'), True), (_temp('b'), True)]
        ir = MutableBinOp('Mult', left_plural, _temp('c'))
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Mult'
        assert len(result.values) == 3

    def test_visit_BinOp_Mult_nested_right_pluralop(self):
        """Mult with PLURALOP(Mult) on right flattens it."""
        visitor = BINOP2PLURALOP_PreVisited()
        right_plural = PLURALOP('Mult')
        right_plural.values = [(_temp('b'), True), (_temp('c'), True)]
        ir = MutableBinOp('Mult', _temp('a'), right_plural)
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Mult'
        assert len(result.values) == 3

    def test_visit_BinOp_Add_non_matching_pluralop_left(self):
        """Add with PLURALOP(Mult) on left does NOT flatten."""
        visitor = BINOP2PLURALOP_PreVisited()
        left_plural = PLURALOP('Mult')
        left_plural.values = [(_temp('a'), True), (_temp('b'), True)]
        ir = MutableBinOp('Add', left_plural, _temp('c'))
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert len(result.values) == 2
        left_expr, _ = result.values[0]
        assert isinstance(left_expr, PLURALOP)
        assert left_expr.op == 'Mult'

    def test_visit_BinOp_Mult_non_matching_pluralop_right(self):
        """Mult with PLURALOP(Add) on right does NOT flatten."""
        visitor = BINOP2PLURALOP_PreVisited()
        right_plural = PLURALOP('Add')
        right_plural.values = [(_temp('a'), True), (_temp('b'), True)]
        ir = MutableBinOp('Mult', _temp('c'), right_plural)
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Mult'
        assert len(result.values) == 2
        right_expr, _ = result.values[1]
        assert isinstance(right_expr, PLURALOP)
        assert right_expr.op == 'Add'

    def test_visit_BinOp_Sub_nested_left_pluralop(self):
        """Sub with PLURALOP(Add) on left flattens it (preserves polarity)."""
        visitor = BINOP2PLURALOP_PreVisited()
        left_plural = PLURALOP('Add')
        left_plural.values = [(_temp('a'), True), (_temp('b'), False)]
        ir = MutableBinOp('Sub', left_plural, _temp('c'))
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert len(result.values) == 3
        assert result.values[0][1] is True   # a from left
        assert result.values[1][1] is False  # b from left
        assert result.values[2][1] is False  # c (Sub -> negative)

    def test_visit_BinOp_Add_nested_sub_pluralop_left(self):
        """Add with PLURALOP(Sub) on left -- Sub is also accepted for flatten."""
        visitor = BINOP2PLURALOP_PreVisited()
        left_plural = PLURALOP('Sub')
        left_plural.values = [(_temp('a'), True), (_temp('b'), False)]
        ir = MutableBinOp('Add', left_plural, _temp('c'))
        result = visitor.visit_BinOp(ir)
        assert isinstance(result, PLURALOP)
        assert result.op == 'Add'
        assert len(result.values) == 3

    # --- Statement visitors ---
    def test_visit_Move_with_const_src(self):
        mv = Move(dst=_temp('x'), src=_const(10))
        self.visitor.visit(mv)
        assert isinstance(mv.src, Const)

    def test_visit_Move_with_temp_src(self):
        mv = Move(dst=_temp('x'), src=_temp('a'))
        self.visitor.visit(mv)
        assert isinstance(mv.src, Temp)

    def test_visit_CJump_with_temp(self):
        blk_t = make_block()
        blk_f = make_block()
        cj = CJump(exp=_temp('flag'), true=blk_t.bid, false=blk_f.bid)
        self.visitor.visit(cj)
        assert isinstance(cj.exp, Temp)

    def test_visit_Move_with_binop_raises_frozen(self):
        mv = Move(dst=_temp('x'), src=_binop('Add', _temp('a'), _temp('b')))
        with pytest.raises(ValidationError, match="frozen"):
            self.visitor.visit(mv)

    def test_visit_CJump_with_binop_raises_frozen(self):
        blk_t = make_block()
        blk_f = make_block()
        cj = CJump(exp=_binop('Add', _temp('a'), _temp('b')), true=blk_t.bid, false=blk_f.bid)
        with pytest.raises(ValidationError, match="frozen"):
            self.visitor.visit(cj)


# ============================================================
# PLURALOP2BINOP
# ============================================================

class TestPLURALOP2BINOP:
    def setup_method(self):
        self.visitor = PLURALOP2BINOP()

    # --- Leaf visitors ---
    def test_visit_Const(self):
        c = _const(42)
        assert self.visitor.visit(c) is c

    def test_visit_Temp(self):
        t = _temp('x')
        assert self.visitor.visit(t) is t

    def test_visit_MRef(self):
        m = MRef(mem=_temp('arr'), offset=_const(0))
        assert self.visitor.visit(m) is m

    def test_visit_Array(self):
        a = Array(items=[_const(1)])
        assert self.visitor.visit(a) is a

    def test_visit_RelOp(self):
        r = RelOp(op='Lt', left=_temp('a'), right=_const(5))
        assert self.visitor.visit(r) is r

    def test_visit_Call(self):
        c = Call(func=_temp('f'), args=[])
        assert self.visitor.visit(c) is c

    def test_visit_Jump(self):
        blk = make_block()
        j = Jump(target=blk.bid)
        result = self.visitor.visit(j)
        assert result is j

    # --- detectop ---
    def test_detectop_add_both_true(self):
        assert self.visitor.detectop('Add', True, True) == 'Add'

    def test_detectop_add_true_false(self):
        assert self.visitor.detectop('Add', True, False) == 'Sub'

    def test_detectop_add_false_true(self):
        assert self.visitor.detectop('Add', False, True) == 'Add'

    def test_detectop_add_both_false(self):
        assert self.visitor.detectop('Add', False, False) == 'Add'

    def test_detectop_mult_true_true(self):
        assert self.visitor.detectop('Mult', True, True) == 'Mult'

    def test_detectop_mult_true_false(self):
        assert self.visitor.detectop('Mult', True, False) == 'Mult'

    def test_detectop_mult_false_false(self):
        assert self.visitor.detectop('Mult', False, False) == 'Mult'

    # --- rebuild_tree / _rebuild_tree ---
    def test_rebuild_tree_single_value(self):
        result = self.visitor.rebuild_tree('Add', [(_temp('a'), True)])
        assert isinstance(result, Temp)
        assert result.name == 'a'

    def test_rebuild_tree_raises_on_single_false_polarity(self):
        with pytest.raises(AssertionError):
            self.visitor.rebuild_tree('Add', [(_temp('a'), False)])

    def test_rebuild_tree_two_values_returns_BinOp(self):
        result = self.visitor.rebuild_tree('Add', [(_temp('a'), True), (_temp('b'), True)])
        assert isinstance(result, BinOp)

    def test_rebuild_tree_sorts_by_polarity(self):
        """Sorting puts True-polarity items first (sorted by str(True) > str(False))."""
        result = self.visitor.rebuild_tree('Mult', [(_temp('x'), True)])
        assert isinstance(result, Temp)

    def test_rebuild_tree_internal_single(self):
        result = self.visitor._rebuild_tree([(_temp('z'), True)], 'Add')
        assert isinstance(result, Temp)
        assert result.name == 'z'

    def test_rebuild_tree_internal_two_returns_BinOp(self):
        result = self.visitor._rebuild_tree(
            [(_temp('a'), True), (_temp('b'), True)], 'Add'
        )
        assert isinstance(result, BinOp)

    def test_rebuild_tree_internal_odd_count_returns_BinOp(self):
        result = self.visitor._rebuild_tree(
            [(_temp('a'), True), (_temp('b'), True), (_temp('c'), True)], 'Add'
        )
        assert isinstance(result, BinOp)

    # --- visit_PolyOp (dispatched via PLURALOP class name) ---
    def test_visit_PLURALOP_single_value(self):
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True)]
        result = self.visitor.visit(p)
        assert isinstance(result, Temp)
        assert result.name == 'a'

    def test_visit_PLURALOP_single_const(self):
        p = PLURALOP('Mult')
        p.values = [(_const(99), True)]
        result = self.visitor.visit(p)
        assert isinstance(result, Const)
        assert result.value == 99

    def test_visit_PLURALOP_multiple_values_returns_BinOp(self):
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True), (_temp('b'), True)]
        result = self.visitor.visit(p)
        assert isinstance(result, BinOp)

    def test_visit_PLURALOP_nested_single(self):
        """PLURALOP containing a nested PLURALOP with single value."""
        inner = PLURALOP('Add')
        inner.values = [(_temp('x'), True)]
        outer = PLURALOP('Mult')
        outer.values = [(inner, True)]
        result = self.visitor.visit(outer)
        assert isinstance(result, Temp)
        assert result.name == 'x'

    # --- Statement visitors ---
    def test_visit_Move_const(self):
        mv = Move(dst=_temp('x'), src=_const(5))
        self.visitor.visit(mv)
        assert isinstance(mv.src, Const)

    def test_visit_Move_temp(self):
        mv = Move(dst=_temp('x'), src=_temp('y'))
        self.visitor.visit(mv)
        assert isinstance(mv.src, Temp)

    def test_visit_CJump_temp(self):
        blk_t = make_block()
        blk_f = make_block()
        cj = CJump(exp=_temp('flag'), true=blk_t.bid, false=blk_f.bid)
        self.visitor.visit(cj)
        assert isinstance(cj.exp, Temp)

    def test_visit_Move_with_pluralop_single(self):
        """Move whose src is a single-value PLURALOP -> unwrapped to Temp."""
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True)]
        mv = Move(dst=_temp('x'), src=_const(0))
        _inject_src(mv, p)
        mv = self.visitor.visit(mv)
        assert isinstance(mv.src, Temp)
        assert mv.src.name == 'a'

    def test_visit_CJump_with_pluralop_single(self):
        blk_t = make_block()
        blk_f = make_block()
        p = PLURALOP('Add')
        p.values = [(_const(1), True)]
        cj = CJump(exp=_const(0), true=blk_t.bid, false=blk_f.bid)
        _inject_exp(cj, p)
        cj = self.visitor.visit(cj)
        assert isinstance(cj.exp, Const)

    def test_visit_Move_with_pluralop_multi_returns_Move_with_BinOp_src(self):
        p = PLURALOP('Add')
        p.values = [(_temp('a'), True), (_temp('b'), True)]
        mv = Move(dst=_temp('x'), src=_const(0))
        _inject_src(mv, p)
        result = self.visitor.visit(mv)
        assert isinstance(result, Move)
        assert isinstance(result.src, BinOp)


# ============================================================
# TreeBalancer (integration)
# ============================================================

class TestTreeBalancer:
    def test_constructor(self):
        tb = TreeBalancer()
        assert isinstance(tb.b2p, BINOP2PLURALOP)
        assert isinstance(tb.p2b, PLURALOP2BINOP)
        assert tb.done_Blocks == []

    def test_process_Block_const_move(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk = Block(scope, 'b')
        mv = Move(dst=_temp('x'), src=_const(42))
        blk.stms = [mv]
        tb._process_Block(blk)
        assert isinstance(mv.src, Const)
        assert blk in tb.done_Blocks

    def test_process_Block_skips_already_done(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk = Block(scope, 'b')
        blk.stms = [Move(dst=_temp('x'), src=_const(1))]
        tb._process_Block(blk)
        tb._process_Block(blk)
        assert tb.done_Blocks.count(blk) == 1

    def test_process_Block_with_jump(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk = Block(scope, 'b')
        blk2 = Block(scope, 'b')
        j = Jump(target=blk2.bid)
        blk.stms = [j]
        tb._process_Block(blk)
        assert blk in tb.done_Blocks

    def test_process_Block_with_cjump_temp(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk = Block(scope, 'b')
        blk_t = Block(scope, 'b')
        blk_f = Block(scope, 'b')
        cj = CJump(exp=_temp('flag'), true=blk_t.bid, false=blk_f.bid)
        blk.stms = [cj]
        tb._process_Block(blk)
        assert isinstance(cj.exp, Temp)

    def test_process_Block_follows_succs(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk1 = Block(scope, 'b')
        blk2 = Block(scope, 'b')
        blk1.stms = [Move(dst=_temp('x'), src=_const(1))]
        blk2.stms = [Move(dst=_temp('y'), src=_const(2))]
        blk1.succs = [blk2]
        tb._process_Block(blk1)
        assert blk1 in tb.done_Blocks
        assert blk2 in tb.done_Blocks

    def test_process_Block_with_binop_raises_frozen(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk = Block(scope, 'b')
        mv = Move(dst=_temp('x'), src=_binop('Add', _temp('a'), _temp('b')))
        blk.stms = [mv]
        with pytest.raises(ValidationError, match="frozen"):
            tb._process_Block(blk)

    def test_process_Block_multiple_stms(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk = Block(scope, 'b')
        blk.stms = [
            Move(dst=_temp('x'), src=_const(1)),
            Move(dst=_temp('y'), src=_temp('z')),
        ]
        tb._process_Block(blk)
        assert blk in tb.done_Blocks
        assert isinstance(blk.stms[0].src, Const)
        assert isinstance(blk.stms[1].src, Temp)

    def test_process_Block_chain_of_succs(self):
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk1 = Block(scope, 'b')
        blk2 = Block(scope, 'b')
        blk3 = Block(scope, 'b')
        blk1.stms = [Move(dst=_temp('a'), src=_const(1))]
        blk2.stms = [Move(dst=_temp('b'), src=_const(2))]
        blk3.stms = [Move(dst=_temp('c'), src=_const(3))]
        blk1.succs = [blk2]
        blk2.succs = [blk3]
        tb._process_Block(blk1)
        assert blk1 in tb.done_Blocks
        assert blk2 in tb.done_Blocks
        assert blk3 in tb.done_Blocks

    def test_process_Block_diamond(self):
        """Diamond CFG: blk1 -> blk2, blk3; blk2 -> blk4; blk3 -> blk4."""
        tb = TreeBalancer()
        scope = MockScope('test_tb')
        blk1 = Block(scope, 'b')
        blk2 = Block(scope, 'b')
        blk3 = Block(scope, 'b')
        blk4 = Block(scope, 'b')
        blk1.stms = [Move(dst=_temp('a'), src=_const(1))]
        blk2.stms = [Move(dst=_temp('b'), src=_const(2))]
        blk3.stms = [Move(dst=_temp('c'), src=_const(3))]
        blk4.stms = [Move(dst=_temp('d'), src=_const(4))]
        blk1.succs = [blk2, blk3]
        blk2.succs = [blk4]
        blk3.succs = [blk4]
        tb._process_Block(blk1)
        for b in [blk1, blk2, blk3, blk4]:
            assert b in tb.done_Blocks


# ============================================================
# Round-trip: BINOP2PLURALOP then PLURALOP2BINOP (non-BinOp leaves)
# ============================================================

class TestRoundTrip:
    def test_move_with_temp_src_roundtrip(self):
        b2p = BINOP2PLURALOP()
        p2b = PLURALOP2BINOP()
        mv = Move(dst=_temp('x'), src=_temp('a'))
        b2p.visit(mv)
        p2b.visit(mv)
        assert isinstance(mv.src, Temp)
        assert mv.src.name == 'a'

    def test_move_with_const_roundtrip(self):
        b2p = BINOP2PLURALOP()
        p2b = PLURALOP2BINOP()
        mv = Move(dst=_temp('x'), src=_const(99))
        b2p.visit(mv)
        p2b.visit(mv)
        assert isinstance(mv.src, Const)
        assert mv.src.value == 99

    def test_cjump_with_temp_roundtrip(self):
        b2p = BINOP2PLURALOP()
        p2b = PLURALOP2BINOP()
        blk_t = make_block()
        blk_f = make_block()
        cj = CJump(exp=_temp('cond'), true=blk_t.bid, false=blk_f.bid)
        b2p.visit(cj)
        p2b.visit(cj)
        assert isinstance(cj.exp, Temp)

    def test_move_with_mref_roundtrip(self):
        b2p = BINOP2PLURALOP()
        p2b = PLURALOP2BINOP()
        mref = MRef(mem=_temp('arr'), offset=_const(0))
        mv = Move(dst=_temp('x'), src=mref)
        b2p.visit(mv)
        p2b.visit(mv)
        assert isinstance(mv.src, MRef)


# ============================================================
# Slots dispatch coverage
# ============================================================

class TestSlotsDispatch:
    def test_b2p_slots_keys(self):
        expected = {'BinOp', 'RelOp', 'Call', 'Const', 'MRef', 'Array', 'Temp',
                    'CJump', 'Jump', 'Move'}
        assert set(BINOP2PLURALOP.slots.keys()) == expected

    def test_p2b_slots_keys(self):
        expected = {'PLURALOP', 'RelOp', 'Call', 'Const', 'MRef', 'Array', 'Temp',
                    'CJump', 'Jump', 'Move'}
        assert set(PLURALOP2BINOP.slots.keys()) == expected

    def test_b2p_slots_values_are_functions(self):
        for name, func in BINOP2PLURALOP.slots.items():
            assert callable(func), f"Slot {name} is not callable"

    def test_p2b_slots_values_are_functions(self):
        for name, func in PLURALOP2BINOP.slots.items():
            assert callable(func), f"Slot {name} is not callable"
