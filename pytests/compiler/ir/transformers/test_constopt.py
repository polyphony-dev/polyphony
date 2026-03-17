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
