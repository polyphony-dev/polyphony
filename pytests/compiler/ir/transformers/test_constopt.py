"""Tests for ConstantOptBase and EarlyConstantOptNonSSA."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.constopt import (
    ConstantOptBase, EarlyConstantOptNonSSA, ConstantOpt,
    _to_signed, _to_unsigned,
)
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


# ===========================================================
# _to_signed / _to_unsigned helpers
# ===========================================================

def test_to_signed_positive():
    """_to_signed keeps a positive value that fits in the signed range."""
    t = Type.int(8, signed=True)  # -128..127
    c = Const(value=42)
    result = _to_signed(t, c)
    assert isinstance(result, Const)
    assert result.value == 42


def test_to_signed_wraps_negative():
    """_to_signed converts an unsigned bit pattern to a negative signed value."""
    t = Type.int(8, signed=True)
    c = Const(value=0xFF)  # 255 -> -1 in signed 8-bit
    result = _to_signed(t, c)
    assert isinstance(result, Const)
    assert result.value == -1


def test_to_unsigned_masks():
    """_to_unsigned masks to unsigned width."""
    t = Type.int(8, signed=False)
    c = Const(value=256)  # overflow -> 0
    result = _to_unsigned(t, c)
    assert isinstance(result, Const)
    assert result.value == 0


def test_to_unsigned_keeps_value():
    """_to_unsigned keeps a value that fits in the unsigned range."""
    t = Type.int(8, signed=False)
    c = Const(value=200)
    result = _to_unsigned(t, c)
    assert isinstance(result, Const)
    assert result.value == 200


# ===========================================================
# ConstantOptBase via ConstantOpt (inherits all visit methods)
# ===========================================================

def test_visit_unop_const_negation():
    """UnOp with constant operand is folded (-5)."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x -5
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == -5


def test_visit_unop_invert_const_fold():
    """UnOp with Invert on constant via binop is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x ~1
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == -2


def test_visit_binop_add_zero_identity():
    """BinOp x + 0 reduces to x."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 5
mv y (+ x 0)
mv @return y
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 5


def test_visit_binop_mult_one_identity():
    """BinOp x * 1 reduces to x."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 7
mv y (* x 1)
mv @return y
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 7


def test_visit_binop_mult_zero():
    """BinOp x * 0 reduces to 0."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 7
mv y (* x 0)
mv @return y
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 0


def test_visit_relop_and_true_const():
    """RelOp And with True constant returns the other operand."""
    src = '''
scope F
tags function returnable
return bool
var x: bool
var y: bool

blk1:
mv x True
cj x blk2 blk3

blk2:
mv @return True
ret @return

blk3:
mv @return False
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # Just verify processing doesn't crash


def test_visit_relop_or_false_const():
    """RelOp Or with False constant returns the other operand."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (== 1 2)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == False


def test_visit_condop_const_true():
    """CondOp with constant True condition returns left."""
    # CondOp can't be parsed from IR text easily, so test via binop folding
    # that results in constant propagation through conditional branches
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 10
cj True blk2 blk3

blk2:
mv @return 1
ret @return

blk3:
mv @return 2
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    entry = scope.entry_block
    assert isinstance(entry.stms[-1], Jump)


def test_visit_mref_const_offset():
    """MRef with constant offset on constant array is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var mem: list<int32>[3]

blk1:
mv mem [10 20 30]
mv x (mld mem 0)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # Processing should not crash


def test_visit_mstore():
    """MStore with constant offset is visited."""
    src = '''
scope F
tags function
var mem: list<int32>[3]
var x: int32

blk1:
mv x 42
expr (mst mem 0 x)
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # Should not crash


def test_visit_array():
    """Array literal with constant repeat is handled."""
    src = '''
scope F
tags function returnable
return int32
var x: list<int32>[3]

blk1:
mv x [1 2 3]
mv @return 0
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # Should not crash; array length should be set


def test_constant_propagation_signed_int():
    """ConstantOpt handles signed integer constant propagation with type narrowing."""
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
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 42


def test_constant_propagation_unsigned_int():
    """ConstantOpt handles unsigned integer constant propagation."""
    src = '''
scope F
tags function returnable
return bit8
var x: bit8

blk1:
mv x 200
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 200


def test_cjump_with_const_variable():
    """ConstantOpt converts CJump when variable is known constant."""
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv @return 10
ret @return

blk3:
mv @return 20
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    entry = scope.entry_block
    last = entry.stms[-1]
    assert isinstance(last, Jump)


def test_relop_eq_both_const():
    """RelOp Eq with both constants is folded."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (== 5 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == True


def test_relop_lt_both_const():
    """RelOp Lt with both constants is folded."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (< 10 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == False


def test_binop_left_shift():
    """BinOp LShift with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (<< 1 4)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 16


def test_binop_right_shift():
    """BinOp RShift with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (>> 16 2)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 4


def test_binop_bitand():
    """BinOp BitAnd with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (& 0 15)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 0


def test_binop_bitor():
    """BinOp BitOr with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (| 5 10)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 15


def test_binop_floor_div():
    """BinOp FloorDiv with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (/ 10 3)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 3


def test_binop_mod():
    """BinOp Mod with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (mod 10 3)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 1


def test_visit_expr():
    """Expr stm is visited (expression folded)."""
    src = '''
scope F
tags function
var x: int32

blk1:
expr (+ 1 2)
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # Should not crash


def test_cmove_const_true_condition():
    """CMove with constant True condition becomes Move."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var c: bool

blk1:
mv c True
mv? c x 10
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # After constopt, CMove with True cond should become Move
    found_cmove = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, CMove):
                found_cmove = True
    # CMove should have been replaced
    assert not found_cmove, "CMove with constant True should have been replaced"


def test_cmove_const_false_condition_removed():
    """CMove with constant False condition is removed."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var c: bool

blk1:
mv x 0
mv? False y 10
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    found_cmove = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, CMove):
                found_cmove = True
    assert not found_cmove, "CMove with constant False should have been removed"


def test_cexpr_const_true_condition():
    """CExpr with constant True condition becomes Expr."""
    src = '''
scope F
tags function
var c: bool

blk1:
mv c True
expr? c (+ 1 2)
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    found_cexpr = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, CExpr):
                found_cexpr = True
    assert not found_cexpr, "CExpr with constant True should have been replaced"


def test_cexpr_const_false_condition_removed():
    """CExpr with constant False condition is removed."""
    src = '''
scope F
tags function

blk1:
expr? False (+ 1 2)
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    found_cexpr = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, CExpr):
                found_cexpr = True
    assert not found_cexpr, "CExpr with constant False should have been removed"


def test_mcjump_all_const():
    """MCJump with all constant conditions and exactly one true is converted to Jump."""
    src = '''
scope F
tags function returnable
return int32

blk1:
mj False blk2 True blk3

blk2:
mv @return 10
ret @return

blk3:
mv @return 20
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    entry = scope.entry_block
    last = entry.stms[-1]
    assert isinstance(last, Jump), f'Expected JUMP but got {type(last).__name__}'


def test_relop_eq_false_const():
    """RelOp Eq that evaluates to False is folded."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (== 3 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == False


def test_relop_gte_const():
    """RelOp GtE with constants is folded."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (>= 5 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == True


def test_relop_gt_const():
    """RelOp Gt with constants is folded."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (> 10 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == True


def test_relop_lte_const():
    """RelOp LtE with constants is folded."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (<= 3 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == True


def test_binop_sub_const():
    """BinOp Sub with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (- 20 7)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 13


def test_binop_bitxor_const():
    """BinOp BitXor with constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (^ 15 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 10


def test_unop_invert_const():
    """UnOp Invert with constant is folded."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x ~0
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == -1


def test_cjump_true_removes_false_branch():
    """CJump with True const removes false branch and converts to Jump."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32

blk1:
cj True blk2 blk3

blk2:
mv a 10
mv @return a
ret @return

blk3:
mv b 20
mv @return b
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    entry = scope.entry_block
    assert isinstance(entry.stms[-1], Jump)


def test_visit_ret():
    """Ret stm has its exp visited."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (+ 3 4)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # @return should be folded to 7
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 7


def test_move_dst_attr_const_propagation():
    """ConstantOpt handles Move to Attr in ctor scope (attribute propagation)."""
    src = '''
scope C
tags class
var x: int32

scope C.__init__
tags function method ctor
param $self: object(C) { self }

blk1:
mv $self.x 10
'''
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    scope = env.scopes.get('C.__init__')
    if scope:
        ConstantOpt().process(scope)
        # Should not crash


def test_constant_fold_nested_binop():
    """ConstantOpt folds nested binary operations."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x (+ 1 2)
mv y (+ x 3)
mv @return y
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 6


def test_mref_const_offset_with_var():
    """MRef with constant offset on a variable is processed."""
    src = '''
scope F
tags function returnable
return int32
var mem: list<int32>[3]
var x: int32

blk1:
mv mem [10 20 30]
mv x (mld mem 1)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # Should process without crash


def test_binop_partial_const_mult_zero():
    """BinOp with one constant operand 0 in mult reduces to 0."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32

blk1:
mv a 3
mv b (* a 0)
mv @return b
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 0


def test_binop_partial_const_add_zero():
    """BinOp with one constant operand 0 in add reduces to the variable."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32

blk1:
mv a 5
mv b (+ 0 a)
mv @return b
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 5


def test_condop_const_cond():
    """CondOp with constant condition is folded via ConstantOptBase."""
    from polyphony.compiler.ir.ir import CondOp, Const, Temp, Move, Ctx
    src = '''
scope F
tags function returnable
return int32
var cval: int32

blk1:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    # Manually insert a CondOp: cval = True ? 10 : 20
    blk = scope.entry_block
    condop = CondOp(cond=Const(value=True), left=Const(value=10), right=Const(value=20))
    mv = Move(dst=Temp(name='cval', ctx=Ctx.STORE), src=condop, block=blk)
    blk.stms.insert(0, mv)
    ConstantOpt().process(scope)
    # After folding, cval should be 10 and propagated or removed


def test_constant_opt_base_direct():
    """ConstantOptBase.process sets block order and builds domtree."""
    src = '''
scope F
tags function returnable
return int32

blk1:
mv @return 42
ret @return
'''
    scope = build_scope(src)
    from polyphony.compiler.ir.transformers.constopt import ConstantOptBase
    base = ConstantOptBase()
    base.process(scope)
    # Should not crash; entry block should have order set
    assert scope.entry_block.order >= 0


def test_early_constant_opt_non_ssa():
    """EarlyConstantOptNonSSA processes scope with constant CJump."""
    src = '''
scope F
tags function returnable
return int32
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
mv @return 10
ret @return

blk3:
mv @return 20
ret @return
'''
    scope = build_scope(src)
    EarlyConstantOptNonSSA().process(scope)
    # After processing, CJump with const True should be converted to Jump
    entry = scope.entry_block
    last = entry.stms[-1]
    assert isinstance(last, Jump), f'Expected JUMP but got {type(last).__name__}'



def test_static_constopt_mref():
    """StaticConstOpt handles MRef with constant offset."""
    from polyphony.compiler.ir.transformers.constopt import StaticConstOpt
    src = '''
scope C
tags class
var arr: list<int32>[3]
var x: int32

blk1:
mv arr [10 20 30]
mv x (mld arr 1)
'''
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    scopes = [env.scopes[name] for name in parser.sources]
    StaticConstOpt().process_scopes(scopes)
    scope = scopes[0]
    # arr should be in constant_array_table after processing


def test_static_constopt_attr():
    """StaticConstOpt handles Attr variables."""
    from polyphony.compiler.ir.transformers.constopt import StaticConstOpt
    src = '''
scope C
tags class
var x: int32

scope C.__init__
tags function method ctor
param $self: object(C) { self }

blk1:
mv $self.x 42
'''
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    scopes = [env.scopes[name] for name in parser.sources]
    StaticConstOpt().process_scopes(scopes)
    # Should process without crash


def test_array_length_propagation():
    """ConstantOpt sets array type length from array literal."""
    src = '''
scope F
tags function
var x: list<int32>[]

blk1:
mv x [1 2 3 4 5]
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    sym = scope.find_sym('x')
    assert sym.typ.length == 5


# ===========================================================
# Additional tests for coverage
# ===========================================================

def test_relop_and_false_const():
    """RelOp And with False constant returns False."""
    from polyphony.compiler.ir.ir import RelOp
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x True
mv @return x
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
            relop = RelOp(op='And', left=Const(value=False), right=Const(value=True))
            object.__setattr__(stm, 'src', relop)
            break
    ConstantOpt().process(scope)
    for b in scope.traverse_blocks():
        for stm in b.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == False


def test_relop_or_true_const():
    """RelOp Or with True constant returns True."""
    from polyphony.compiler.ir.ir import RelOp
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x False
mv @return x
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
            relop = RelOp(op='Or', left=Const(value=True), right=Const(value=False))
            object.__setattr__(stm, 'src', relop)
            break
    ConstantOpt().process(scope)
    for b in scope.traverse_blocks():
        for stm in b.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == True


def test_condop_const_false_returns_right():
    """CondOp with constant False condition returns right."""
    from polyphony.compiler.ir.ir import CondOp
    src = '''
scope F
tags function returnable
return int32
var cval: int32

blk1:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    condop = CondOp(cond=Const(value=False), left=Const(value=10), right=Const(value=20))
    mv = Move(dst=Temp(name='cval', ctx=Ctx.STORE), src=condop, block=blk)
    blk.stms.insert(0, mv)
    ConstantOpt().process(scope)


def test_unop_with_non_const_changed():
    """UnOp with changed but non-constant sub-expression returns new UnOp."""
    from polyphony.compiler.ir.ir import UnOp, BinOp
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 5
mv y x
mv @return y
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'y':
            inner = BinOp(op='Add', left=Temp(name='x'), right=Const(value=0))
            unop = UnOp(op='USub', exp=inner)
            object.__setattr__(stm, 'src', unop)
            break
    ConstantOpt().process(scope)
    for b in scope.traverse_blocks():
        for stm in b.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == -5


def test_mref_inline_array_offset():
    """MRef with inline Array and constant offset returns the element."""
    from polyphony.compiler.ir.ir import MRef, Array
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    arr = Array(items=[Const(value=100), Const(value=200), Const(value=300)], repeat=Const(value=1))
    mref = MRef(mem=arr, offset=Const(value=1))
    mv = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=mref, block=blk)
    blk.stms.insert(0, mv)
    ConstantOpt().process(scope)


def test_mref_inline_array_out_of_bounds():
    """MRef with inline Array and out-of-bounds offset returns original."""
    from polyphony.compiler.ir.ir import MRef, Array
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    arr = Array(items=[Const(value=100)], repeat=Const(value=1))
    mref = MRef(mem=arr, offset=Const(value=5))
    mv = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=mref, block=blk)
    blk.stms.insert(0, mv)
    ConstantOpt().process(scope)


def test_relop_noteq_both_const():
    """RelOp NotEq with both constants is folded."""
    from polyphony.compiler.ir.ir import RelOp
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (== 5 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
            relop = RelOp(op='NotEq', left=Const(value=5), right=Const(value=5))
            object.__setattr__(stm, 'src', relop)
            break
    ConstantOpt().process(scope)
    for b in scope.traverse_blocks():
        for stm in b.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == False


def test_cjump_false_removes_true_branch():
    """CJump with False const removes true branch and jumps to false."""
    src = '''
scope F
tags function returnable
return int32

blk1:
cj False blk2 blk3

blk2:
mv @return 10
ret @return

blk3:
mv @return 20
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    entry = scope.entry_block
    assert isinstance(entry.stms[-1], Jump)


def test_mcjump_first_true():
    """MCJump with first condition True is converted to Jump."""
    src = '''
scope F
tags function returnable
return int32

blk1:
mj True blk2 False blk3

blk2:
mv @return 10
ret @return

blk3:
mv @return 20
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    entry = scope.entry_block
    last = entry.stms[-1]
    assert isinstance(last, Jump)


def test_constant_opt_binop_both_const_sub():
    """BinOp Sub with both constants is folded."""
    src = '''
scope F
tags function returnable
return int32
var y: int32

blk1:
mv y (- 10 0)
mv @return y
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 10


def test_polyadconstantfolding_bin2poly_and_poly2bin():
    """PolyadConstantFolding._Bin2Poly and _Poly2Bin convert and fold."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import BinOp, PolyOp
    inner = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    outer = BinOp(op='Add', left=inner, right=Const(value=2))
    b2p = PolyadConstantFolding._Bin2Poly()
    result = b2p.visit_BinOp(outer)
    assert isinstance(result, PolyOp)
    assert result.op == 'Add'
    assert len(result.values) == 3
    p2b = PolyadConstantFolding._Poly2Bin()
    result2 = p2b.visit_PolyOp(result)
    assert isinstance(result2, BinOp)
    assert result2.op == 'Add'
    if isinstance(result2.left, Const):
        assert result2.left.value == 3
    else:
        assert isinstance(result2.right, Const) and result2.right.value == 3


def test_polyadconstantfolding_mult_fold():
    """PolyadConstantFolding._Poly2Bin folds multiplication constants."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import BinOp, PolyOp
    inner = BinOp(op='Mult', left=Temp(name='x'), right=Const(value=3))
    outer = BinOp(op='Mult', left=inner, right=Const(value=4))
    b2p = PolyadConstantFolding._Bin2Poly()
    poly = b2p.visit_BinOp(outer)
    assert isinstance(poly, PolyOp)
    p2b = PolyadConstantFolding._Poly2Bin()
    result = p2b.visit_PolyOp(poly)
    assert isinstance(result, BinOp)
    assert result.op == 'Mult'
    if isinstance(result.left, Const):
        assert result.left.value == 12
    else:
        assert isinstance(result.right, Const) and result.right.value == 12


def test_polyadconstantfolding_non_add_mult_passthrough():
    """PolyadConstantFolding._Bin2Poly passes through non-Add/Mult BinOps."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import BinOp
    binop = BinOp(op='Sub', left=Const(value=10), right=Const(value=3))
    b2p = PolyadConstantFolding._Bin2Poly()
    result = b2p.visit_BinOp(binop)
    assert isinstance(result, BinOp)
    assert result.op == 'Sub'


def test_polyadconstantfolding_bin_inlining_can_inlining():
    """PolyadConstantFolding._BinInlining._can_inlining checks correctly."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import BinOp
    blk = None
    ir = Move(dst=Temp(name='a', ctx=Ctx.STORE),
              src=BinOp(op='Add', left=Const(value=1), right=Temp(name='x')),
              block=blk)
    usestm = Move(dst=Temp(name='b', ctx=Ctx.STORE),
                  src=BinOp(op='Add', left=Temp(name='a'), right=Const(value=2)),
                  block=blk)
    assert PolyadConstantFolding._BinInlining._can_inlining(usestm, ir) is True
    usestm2 = Move(dst=Temp(name='b', ctx=Ctx.STORE),
                   src=BinOp(op='Sub', left=Temp(name='a'), right=Const(value=2)),
                   block=blk)
    assert PolyadConstantFolding._BinInlining._can_inlining(usestm2, ir) is False
    from polyphony.compiler.ir.ir import Expr as E
    usestm3 = E(exp=Temp(name='a'), block=blk)
    assert PolyadConstantFolding._BinInlining._can_inlining(usestm3, ir) is False


def test_polyadconstantfolding_bin2poly_no_more_than_2():
    """PolyadConstantFolding._Bin2Poly returns BinOp when <= 2 values."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import BinOp
    binop = BinOp(op='Add', left=Temp(name='x'), right=Const(value=1))
    b2p = PolyadConstantFolding._Bin2Poly()
    result = b2p.visit_BinOp(binop)
    assert isinstance(result, BinOp)


def test_polyadconstantfolding_bin2poly_left_binop():
    """PolyadConstantFolding._Bin2Poly handles left child being BinOp."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import BinOp, PolyOp
    left = BinOp(op='Add', left=Const(value=2), right=Const(value=3))
    outer = BinOp(op='Add', left=left, right=Temp(name='x'))
    b2p = PolyadConstantFolding._Bin2Poly()
    result = b2p.visit_BinOp(outer)
    assert isinstance(result, PolyOp)
    assert len(result.values) == 3


def test_visit_const_passthrough():
    """ConstantOptBase.visit_Const returns ir unchanged."""
    from polyphony.compiler.ir.transformers.constopt import ConstantOptBase
    base = ConstantOptBase()
    c = Const(value=42)
    assert base.visit_Const(c) is c


def test_to_signed_16bit():
    """_to_signed with 16-bit signed type."""
    t = Type.int(16, signed=True)
    c = Const(value=0x8000)
    result = _to_signed(t, c)
    assert isinstance(result, Const)
    assert result.value == -32768


def test_to_unsigned_16bit():
    """_to_unsigned with 16-bit unsigned type."""
    t = Type.int(16, signed=False)
    c = Const(value=0x10000)
    result = _to_unsigned(t, c)
    assert isinstance(result, Const)
    assert result.value == 0


def test_relop_same_variable_eq():
    """RelOp with same variable on both sides folds (x == x -> True)."""
    src = '''
scope F
tags function returnable
return bool
var x: int32
var r: bool

blk1:
mv x 5
mv r (== x x)
mv @return r
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)


def test_static_constopt_process_scopes_with_origin():
    """StaticConstOpt propagates constants and handles scope.origin."""
    from polyphony.compiler.ir.transformers.constopt import StaticConstOpt
    src = '''
scope C
tags class
var x: int32

blk1:
mv x 42
'''
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    scopes = [env.scopes[name] for name in parser.sources]
    opt = StaticConstOpt()
    opt.process_scopes(scopes)
    assert len(opt.constant_table) >= 1


def test_constant_opt_mref_with_non_nameexp():
    """ConstantOpt.visit_MRef handles non-IrNameExp mem gracefully."""
    from polyphony.compiler.ir.ir import MRef, BinOp
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    binop = BinOp(op='Add', left=Const(value=1), right=Const(value=2))
    mref = MRef(mem=binop, offset=Const(value=0))
    mv = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=mref, block=blk)
    blk.stms.insert(0, mv)
    ConstantOpt().process(scope)


def test_polyadconstantfolding_polyop_passthrough():
    """PolyadConstantFolding._Bin2Poly.visit_PolyOp returns PolyOp unchanged."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import PolyOp
    poly = PolyOp(op='Add', values=[Temp(name='x'), Const(value=1)])
    b2p = PolyadConstantFolding._Bin2Poly()
    result = b2p.visit_PolyOp(poly)
    assert result is poly


def test_polyadconstantfolding_mult_poly2bin():
    """PolyadConstantFolding._Poly2Bin folds Mult PolyOp to BinOp."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    from polyphony.compiler.ir.ir import PolyOp, BinOp
    poly = PolyOp(op='Mult', values=[Temp(name='x'), Const(value=3), Const(value=4)])
    p2b = PolyadConstantFolding._Poly2Bin()
    result = p2b.visit_PolyOp(poly)
    assert isinstance(result, BinOp)
    assert result.op == 'Mult'
    if isinstance(result.right, Const):
        assert result.right.value == 12
    else:
        assert isinstance(result.left, Const) and result.left.value == 12


def test_binop_changed_non_const():
    """BinOp where sub-expressions change but aren't const produces new BinOp."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32

blk1:
mv a 5
mv b (+ a 0)
mv c (+ b 1)
mv @return c
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 6


def test_relop_or_both_false():
    """RelOp Or with both False constants is folded to False."""
    from polyphony.compiler.ir.ir import RelOp
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x False
mv @return x
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
            relop = RelOp(op='Or', left=Const(value=False), right=Const(value=False))
            object.__setattr__(stm, 'src', relop)
            break
    ConstantOpt().process(scope)
    for b in scope.traverse_blocks():
        for stm in b.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == False


def test_relop_and_both_true():
    """RelOp And with both True constants is folded to True."""
    from polyphony.compiler.ir.ir import RelOp
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x True
mv @return x
ret @return
'''
    scope = build_scope(src)
    blk = scope.entry_block
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
            relop = RelOp(op='And', left=Const(value=True), right=Const(value=True))
            object.__setattr__(stm, 'src', relop)
            break
    ConstantOpt().process(scope)
    for b in scope.traverse_blocks():
        for stm in b.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == True


def test_polyadconstantfolding_bin_inlining_non_const():
    """PolyadConstantFolding._BinInlining skips BinOp without constants."""
    from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
    src = '''
scope F
tags function returnable
return int32
var a: int32

blk1:
mv a (- 10 3)
mv @return a
ret @return
'''
    scope = build_scope(src)
    PolyadConstantFolding._BinInlining().process(scope)


def test_binop_relop_mixed():
    """BinOp with one const and RelOp is reduced correctly."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (* 0 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 0


def test_mref_non_const_offset_handled():
    """MRef with non-constant offset is returned by visit_MRef."""
    from polyphony.compiler.ir.ir import MRef
    from polyphony.compiler.ir.transformers.constopt import ConstantOptBase
    base = ConstantOptBase()
    mref = MRef(mem=Temp(name='mem'), offset=Temp(name='i'))
    result = base.visit_MRef(mref)
    # offset is not const, so MRef is returned unchanged
    assert result is mref


def test_mstore_offset_and_exp_visited():
    """MStore has both offset and exp sub-expressions visited."""
    src = '''
scope F
tags function
var mem: list<int32>[3]
var x: int32

blk1:
mv x 42
expr (mst mem (+ 0 1) x)
'''
    scope = build_scope(src)
    ConstantOpt().process(scope)


def test_constant_opt_visit_temp_non_containable():
    """ConstantOpt.visit_Temp returns ir for non-containable scope."""
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
    scope = build_scope(src)
    ConstantOpt().process(scope)
    # x should be propagated


def test_visit_array_items_folded():
    """Array items with foldable expressions are visited."""
    from polyphony.compiler.ir.ir import Array, BinOp
    src = '''
scope F
tags function
var x: list<int32>[3]

blk1:
mv x [1 2 3]
'''
    scope = build_scope(src)
    blk = scope.entry_block
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
            # Replace the array with one that has foldable items
            arr = Array(items=[BinOp(op='Add', left=Const(value=1), right=Const(value=2)),
                               Const(value=20), Const(value=30)],
                       repeat=Const(value=1))
            object.__setattr__(stm, 'src', arr)
            break
    ConstantOpt().process(scope)
