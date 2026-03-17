"""Tests for EarlyQuadrupleMaker and LateQuadrupleMaker."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import name2var as _v
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.quadruplet import (
    EarlyQuadrupleMaker, LateQuadrupleMaker,
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
# EarlyQuadrupleMaker
# ===========================================================

def test_early_const_passthrough():
    """Const values pass through unchanged."""
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
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    assert len(moves) == 2
    assert isinstance(moves[0].src, Const)
    assert moves[0].src.value == 42


def test_early_binop_in_move_suppressed():
    """BinOp in a Move src stays as BinOp (suppress=True)."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32

blk1:
mv a 1
mv b 2
mv c (+ a b)
mv @return c
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    c_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'c']
    assert len(c_move) == 1
    assert isinstance(c_move[0].src, BinOp)


def test_early_relop_in_move_suppressed():
    """RelOp in a Move src stays as RelOp (suppress=True)."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var cond: bool

blk1:
mv a 5
mv cond (== a 10)
mv @return a
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    cond_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'cond']
    assert len(cond_move) == 1
    assert isinstance(cond_move[0].src, RelOp)


def test_early_nested_binop_extracted():
    """A nested BinOp expression is decomposed: the inner BinOp is extracted
    to a temp move, and the outer BinOp uses the temp."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32
var d: int32

blk1:
mv a 1
mv b 2
mv c 3
mv d (+ (+ a b) c)
mv @return d
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    d_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'd']
    assert len(d_move) == 1
    assert isinstance(d_move[0].src, BinOp)
    # The left operand of d's BinOp should be a Temp (the extracted temp)
    assert isinstance(d_move[0].src.left, Temp)


def test_early_unop_visited():
    """UnOp with a Temp operand is visited and kept in Move src."""
    setup_test()
    scope = Scope.create(None, 'UnOpTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('a', tags=set(), typ=Type.int())
    scope.add_sym('b', tags=set(), typ=Type.int())

    blk = Block(scope, nametag='entry')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    blk.append_stm(Move(Temp('a', Ctx.STORE), Const(5)))
    blk.append_stm(Move(Temp('b', Ctx.STORE), UnOp('USub', Temp('a'))))
    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('b')))
    blk.append_stm(Ret(Temp('@return')))
    Block.set_order(blk, 0)

    EarlyQuadrupleMaker().process(scope)
    moves = [s for s in scope.entry_block.stms if isinstance(s, Move)]
    b_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'b']
    assert len(b_move) == 1
    assert isinstance(b_move[0].src, UnOp)


def test_early_mref_load_in_move_suppressed():
    """MRef in a Move src stays as MRef (suppress=True for MRef in Move)."""
    src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var idx: int32
var result: int32

blk1:
mv idx 0
mv result (mld arr idx)
mv @return result
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    res_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'result']
    assert len(res_move) == 1
    assert isinstance(res_move[0].src, MRef)


def test_early_mstore_expr():
    """expr (mst ...) is preserved by the quadruple maker."""
    src = '''
scope F
tags function
var arr: list<int32>[4]
var idx: int32

blk1:
mv idx 0
expr (mst arr idx 42)
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    exprs = [s for s in blk.stms if isinstance(s, Expr)]
    ms_expr = [e for e in exprs if isinstance(e.exp, MStore)]
    assert len(ms_expr) == 1


def test_early_call_in_move_suppressed():
    """Call in a Move src stays as Call (suppress=True)."""
    src = '''
scope F
tags function returnable
return int32
var result: int32

blk1:
mv result (call @F)
mv @return result
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    res_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'result']
    assert len(res_move) == 1
    assert isinstance(res_move[0].src, Call)


def test_early_syscall_in_move_suppressed():
    """SysCall in a Move src stays as SysCall (suppress=True)."""
    src = '''
scope F
tags function returnable
return int32
var result: int32

blk1:
mv result (syscall $len)
mv @return result
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    res_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'result']
    assert len(res_move) == 1
    assert isinstance(res_move[0].src, SysCall)


def test_early_call_in_expr_suppressed():
    """Call in an Expr stays as Expr (suppress=True for Call in Expr)."""
    src = '''
scope F
tags function returnable
return int32

blk1:
expr (call @F)
mv @return 0
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    exprs = [s for s in blk.stms if isinstance(s, Expr) and not isinstance(s, CExpr)]
    call_exprs = [e for e in exprs if isinstance(e.exp, Call)]
    assert len(call_exprs) == 1


def test_early_cjump_condition():
    """CJump condition should be a Temp (condition sym) or Const after quadruple."""
    setup_test()
    scope = Scope.create(None, 'CJTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('a', tags=set(), typ=Type.int())
    cond_sym = scope.add_condition_sym()

    blk1 = Block(scope, nametag='entry')
    blk2 = Block(scope, nametag='then')
    blk3 = Block(scope, nametag='else')
    scope.set_entry_block(blk1)
    scope.set_exit_block(blk3)

    blk1.append_stm(Move(Temp('a', Ctx.STORE), Const(5)))
    blk1.append_stm(Move(Temp(cond_sym.name, Ctx.STORE), RelOp('Lt', Temp('a'), Const(10))))
    blk1.append_stm(CJump(Temp(cond_sym.name), blk2, blk3))
    blk1.connect(blk2)
    blk1.connect(blk3)

    blk2.append_stm(Move(Temp('@return', Ctx.STORE), Const(1)))
    blk2.append_stm(Ret(Temp('@return')))

    blk3.append_stm(Move(Temp('@return', Ctx.STORE), Const(0)))
    blk3.append_stm(Ret(Temp('@return')))

    Block.set_order(blk1, 0)

    EarlyQuadrupleMaker().process(scope)
    entry = scope.entry_block
    cjumps = [s for s in entry.stms if isinstance(s, CJump)]
    assert len(cjumps) == 1
    assert isinstance(cjumps[0].exp, (Temp, Const))


def test_early_condop_extracted():
    """CondOp expression is always extracted to a temp move."""
    setup_test()
    scope = Scope.create(None, 'CondTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('a', tags=set(), typ=Type.int())
    scope.add_sym('cond', tags=set(), typ=Type.bool())
    scope.add_sym('result', tags=set(), typ=Type.int())

    blk = Block(scope, nametag='entry')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    blk.append_stm(Move(Temp('a', Ctx.STORE), Const(5)))
    blk.append_stm(Move(Temp('cond', Ctx.STORE), RelOp('Lt', Temp('a'), Const(10))))
    condop = CondOp(cond=Temp('cond'), left=Const(1), right=Const(0))
    blk.append_stm(Move(Temp('result', Ctx.STORE), condop))
    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('result')))
    blk.append_stm(Ret(Temp('@return')))
    Block.set_order(blk, 0)

    EarlyQuadrupleMaker().process(scope)
    moves = [s for s in scope.entry_block.stms if isinstance(s, Move)]
    res_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'result']
    assert len(res_move) == 1
    # CondOp is extracted to a temp, so result gets a Temp
    assert isinstance(res_move[0].src, Temp)


def test_early_array_items_visited():
    """Array items are visited by the transformer."""
    src = '''
scope F
tags function
var arr: list<int32>[3]
var a: int32
var b: int32
var c: int32

blk1:
mv a 1
mv b 2
mv c 3
mv arr [a, b, c]
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    arr_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'arr']
    assert len(arr_move) == 1
    assert isinstance(arr_move[0].src, Array)


def test_early_attr_passthrough():
    """Attr expression passes through (visiting its sub-expression)."""
    setup_test()
    src = '''
scope @top.M
tags module class instantiated
var x: int32

scope @top.M.f
tags method returnable
param self: object(@top.M)
return int32

blk1:
mv @return self.x
ret @return
'''
    IRParser(src).parse_scope()
    scope = env.scopes['@top.M.f']
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    ret_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == '@return']
    assert len(ret_move) == 1
    assert isinstance(ret_move[0].src, Attr)


def test_early_mcjump():
    """MCJump conditions are visited and remain Temp or Const."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var c1: bool
var c2: bool

blk1:
mv a 5
mv c1 (< a 10)
mv c2 (> a 0)
mj c1 blk2 c2 blk3 1 blk4

blk2:
mv @return 1
ret @return

blk3:
mv @return 2
ret @return

blk4:
mv @return 3
ret @return
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    entry = scope.entry_block
    mcjumps = [s for s in entry.stms if isinstance(s, MCJump)]
    assert len(mcjumps) == 1
    for cond in mcjumps[0].conds:
        assert isinstance(cond, (Temp, Const))


def test_early_new_in_move_suppressed():
    """New (via SysCall $new) in a Move src stays suppressed."""
    setup_test()
    src = '''
scope @top.M
tags module class instantiated

scope @top.M.__init__
tags ctor method
param self: object(@top.M)
var obj: object(@top.M)

blk1:
mv obj (syscall $new M)
'''
    IRParser(src).parse_scope()
    scope = env.scopes['@top.M.__init__']
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    obj_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'obj']
    assert len(obj_move) == 1
    assert isinstance(obj_move[0].src, SysCall)


def test_early_mstore_in_expr_suppressed():
    """MStore in an Expr passes through (suppress for MStore in Expr)."""
    src = '''
scope F
tags function
var arr: list<int32>[4]
var idx: int32

blk1:
mv idx 0
expr (mst arr idx 99)
'''
    scope = build_scope(src)
    EarlyQuadrupleMaker().process(scope)
    blk = scope.entry_block
    exprs = [s for s in blk.stms if isinstance(s, Expr)]
    ms_exprs = [e for e in exprs if isinstance(e.exp, MStore)]
    assert len(ms_exprs) == 1


def test_early_nested_mref_in_mref():
    """Nested MRef (MRef as mem of outer MRef) is handled."""
    setup_test()
    scope = Scope.create(None, 'NestedMRef', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    scope.add_sym('arr', tags=set(), typ=Type.list(Type.list(Type.int(), 4), 4))
    scope.add_sym('i', tags=set(), typ=Type.int())
    scope.add_sym('j', tags=set(), typ=Type.int())
    scope.add_sym('result', tags=set(), typ=Type.int())

    blk = Block(scope, nametag='entry')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    blk.append_stm(Move(Temp('i', Ctx.STORE), Const(0)))
    blk.append_stm(Move(Temp('j', Ctx.STORE), Const(1)))
    # arr[i][j] => MRef(MRef(arr, i), j)
    inner_mref = MRef(Temp('arr'), Temp('i'), Ctx.LOAD)
    outer_mref = MRef(inner_mref, Temp('j'), Ctx.LOAD)
    blk.append_stm(Move(Temp('result', Ctx.STORE), outer_mref))
    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('result')))
    blk.append_stm(Ret(Temp('@return')))
    Block.set_order(blk, 0)

    EarlyQuadrupleMaker().process(scope)
    moves = [s for s in scope.entry_block.stms if isinstance(s, Move)]
    res_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'result']
    assert len(res_move) == 1
    # The nested MRef should be handled (inner extracted or kept)
    assert isinstance(res_move[0].src, MRef)


def test_early_array_mult_binop():
    """Array * N in a BinOp is handled: Array gets updated repeat."""
    setup_test()
    scope = Scope.create(None, 'ArrayMult', {'function'}, 0)
    scope.return_type = Type.none()
    scope.add_sym('arr', tags=set(), typ=Type.list(Type.int(), 4))

    blk = Block(scope, nametag='entry')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)

    arr = Array(items=[Const(0)], repeat=Const(1), mutable=True)
    binop = BinOp(op='Mult', left=arr, right=Const(4))
    blk.append_stm(Move(Temp('arr', Ctx.STORE), binop))
    Block.set_order(blk, 0)

    EarlyQuadrupleMaker().process(scope)
    moves = [s for s in scope.entry_block.stms if isinstance(s, Move)]
    arr_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == 'arr']
    assert len(arr_move) == 1
    assert isinstance(arr_move[0].src, Array)
    assert arr_move[0].src.repeat == Const(4)


# ===========================================================
# LateQuadrupleMaker
# ===========================================================

def test_late_attr_scalar_passthrough():
    """LateQuadrupleMaker keeps scalar Attr references unchanged."""
    setup_test()
    src = '''
scope @top.M
tags module class instantiated
var x: int32

scope @top.M.f
tags method returnable
param self: object(@top.M)
return int32

blk1:
mv @return self.x
ret @return
'''
    IRParser(src).parse_scope()
    scope = env.scopes['@top.M.f']
    LateQuadrupleMaker().process(scope)
    blk = scope.entry_block
    moves = [s for s in blk.stms if isinstance(s, Move)]
    ret_move = [m for m in moves if isinstance(m.dst, Temp) and m.dst.name == '@return']
    assert len(ret_move) == 1
    assert isinstance(ret_move[0].src, Attr)
