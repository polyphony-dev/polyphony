from collections import deque
from typing import cast
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irhelper import qualified_symbols
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope, FunctionScope, ClassScope, NamespaceScope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test
import pytest


def test_type_1():
    setup_test()
    parser = IrReader('')
    t = parser.parse_type('int8')
    assert t.is_int()
    assert t.width == 8
    assert t.signed is True

    t = parser.parse_type('int32')
    assert t.is_int()
    assert t.width == 32
    assert t.signed is True

    t = parser.parse_type('bit32')
    assert t.is_int()
    assert t.width == 32
    assert t.signed is False


def test_type_2():
    setup_test()
    parser = IrReader('')
    t = parser.parse_type('list<bool>[8]')
    assert t.is_list()
    assert t.element.is_bool()
    assert t.length == 8

    t = parser.parse_type('tuple<int32>[100]')
    assert t.is_tuple()
    assert t.element.is_int()
    assert t.element.width == 32
    assert t.length == 100


def test_type_3():
    setup_test()
    parser = IrReader('')
    t = parser.parse_type('list<bool>[]')
    assert t.is_list()
    assert t.element.is_bool()
    assert t.length == Type.ANY_LENGTH

    t = parser.parse_type('tuple<int32>[]')
    assert t.is_tuple()
    assert t.element.is_int()
    assert t.element.width == 32
    assert t.length == Type.ANY_LENGTH


def test_type_4():
    setup_test()
    parser = IrReader('')
    top = env.scopes['@top']
    X = Scope.create(top, 'X', {'class'}, 0)
    F = Scope.create(top, 'F', {'function'}, 0)

    t = parser.parse_type('object(@top.X)')
    assert t.is_object()
    assert t.scope is X

    t = parser.parse_type('class(@top.X)')
    assert t.is_class()
    assert t.scope is X

    t = parser.parse_type('namespace(@top)')
    assert t.is_namespace()
    assert t.scope is top

    t = parser.parse_type('function(@top.F)')
    assert t.is_function()
    assert t.scope is F


def test_var_1():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope
    scope.add_sym('a', tags=set(), typ=Type.int(8))

    v = parser.parse_scalar('a')
    t = cast(Temp, v)
    assert isinstance(t, Temp)
    assert t.name == 'a'
    sym = cast(Symbol, qualified_symbols(t, scope)[-1])
    assert isinstance(sym, Symbol)
    assert sym.typ.is_int()
    assert sym.name == 'a'
    assert sym.scope is scope

def test_var_2():
    setup_test()
    parser = IrReader('')
    X = Scope.create(None, 'X', {'class'}, 0)
    X.add_sym('value', tags=set(), typ=Type.int(8))
    Y = Scope.create(None, 'Y', {'class'}, 0)
    Y.add_sym('x', tags=set(), typ=Type.object(X))

    parser.current_scope = Y
    x = parser.parse_scalar('x')
    x = cast(Temp, x)
    assert isinstance(x, Temp)
    assert x.name == 'x'
    x_sym = cast(Symbol, qualified_symbols(x, Y)[-1])
    assert x_sym.typ.is_object()
    assert x_sym.typ.scope is X
    assert x_sym.scope is Y

    xv = parser.parse_scalar('x.value')
    xv = cast(Attr, xv)
    assert isinstance(xv, Attr)
    xv_sym = cast(Symbol, qualified_symbols(xv, Y)[-1])
    assert xv_sym.name == 'value'
    assert xv_sym.typ.is_int()
    assert xv_sym.typ.width == 8
    assert xv_sym.scope is X

def test_var_3():
    setup_test()
    parser = IrReader('')
    X = Scope.create(None, 'X', {'class'}, 0)
    X.add_sym('value', tags=set(), typ=Type.int(8))
    Y = Scope.create(None, 'Y', {'class'}, 0)
    Y.add_sym('x', tags=set(), typ=Type.object(X))
    Z = Scope.create(None, 'Z', {'class'}, 0)
    Z.add_sym('y', tags=set(), typ=Type.object(Y))

    parser.current_scope = Z
    y = parser.parse_scalar('y')
    y = cast(Temp, y)
    assert isinstance(y, Temp)
    y_sym = cast(Symbol, qualified_symbols(y, Z)[-1])
    assert y_sym.name == 'y'
    assert y_sym.typ.is_object()
    assert y_sym.typ.scope is Y
    assert y_sym.scope is Z

    yx = parser.parse_scalar('y.x')
    yx = cast(Attr, yx)
    assert isinstance(yx, Attr)
    assert isinstance(yx.exp, Temp)
    assert yx.exp.name == 'y'
    assert yx.name == 'x'
    yx_sym = cast(Symbol, qualified_symbols(yx, Z)[-1])
    assert yx_sym.typ.is_object()
    assert yx_sym.typ.scope is X
    assert yx_sym.scope is Y

    yxv = parser.parse_var('y.x.value', Ctx.STORE)
    yxv = cast(Attr, yxv)
    assert isinstance(yxv, Attr)
    assert yxv.ctx == Ctx.STORE
    assert isinstance(yxv.exp, Attr)
    assert yxv.exp.name == 'x'
    assert yxv.exp.ctx == Ctx.LOAD
    assert yxv.exp.exp.name == 'y'
    assert yxv.exp.exp.ctx == Ctx.LOAD
    assert yxv.name == 'value'
    yxv_sym = cast(Symbol, qualified_symbols(yxv, Z)[-1])
    assert yxv_sym.typ.is_int()
    assert yxv_sym.scope is X

def test_var_4():
    setup_test()
    parser = IrReader('')
    v = parser.parse_scalar('123')
    v = cast(Const, v)
    assert isinstance(v, Const)
    assert v.value == 123

    v = parser.parse_scalar('-123')
    v = cast(UnOp, v)
    assert isinstance(v, UnOp)
    assert v.op == 'USub'
    assert isinstance(v.exp, Const)
    assert cast(Const, v.exp).value == 123

    v = parser.parse_scalar('+123')
    v = cast(UnOp, v)
    assert isinstance(v, UnOp)
    assert v.op == 'UAdd'
    assert isinstance(v.exp, Const)
    assert cast(Const, v.exp).value == 123


def test_var_5():
    setup_test()
    parser = IrReader('')
    p = parser.parse_scalar('@in_x')
    assert isinstance(p, Temp)
    p = cast(Temp, p)
    assert p.name == '@in_x'

    p = parser.parse_scalar('_x#1')
    assert isinstance(p, Temp)
    p = cast(Temp, p)
    assert p.name == '_x#1'

    p = parser.parse_scalar('!assert')
    assert isinstance(p, Temp)
    p = cast(Temp, p)
    assert p.name == '!assert'


def test_var_6():
    setup_test()
    parser = IrReader('')
    p = parser.parse_scalar('True')
    assert p == Const(True)

    p = parser.parse_scalar('False')
    assert p == Const(False)


def test_var_7():
    setup_test()
    parser = IrReader('')
    p = parser.parse_scalar("'text'")
    assert p == Const('text')

    p = parser.parse_scalar('"TEXT"')
    assert p == Const('TEXT')


def test_block_line():
    setup_test()
    src = '''
    mv a 1
    mv b -a
    mv c (+ a b)
    '''
    parser = IrReader(src)
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope
    a = scope.add_sym('a', tags=set(), typ=Type.int(8))
    b = scope.add_sym('b', tags=set(), typ=Type.int(10))
    c = scope.add_sym('c', tags=set(), typ=Type.int(12))
    blk = Block(scope)
    parser.current_block = blk
    scope.set_entry_block(blk)

    assert parser.parse_block_line()
    stm = blk.stms[0]
    assert isinstance(stm, Move)
    assert isinstance(stm.dst, Temp)
    assert stm.dst.ctx == Ctx.STORE
    dst_sym = cast(Symbol, qualified_symbols(stm.dst, scope)[-1])
    assert dst_sym is a
    assert isinstance(stm.src, Const)
    assert stm.src.value == 1

    assert parser.parse_block_line()
    stm = blk.stms[1]
    assert isinstance(stm, Move)
    assert isinstance(stm.dst, Temp)
    assert stm.dst.ctx == Ctx.STORE
    dst_sym = cast(Symbol, qualified_symbols(stm.dst, scope)[-1])
    assert dst_sym is b
    assert isinstance(stm.src, UnOp)
    assert stm.src.op == 'USub'
    assert isinstance(stm.src.exp, Temp)
    src_sym = cast(Symbol, qualified_symbols(stm.src.exp, scope)[-1])
    assert src_sym is a

    assert parser.parse_block_line()
    stm = blk.stms[2]
    assert isinstance(stm, Move)
    assert isinstance(stm.dst, Temp)
    assert stm.dst.ctx == Ctx.STORE
    dst_sym = cast(Symbol, qualified_symbols(stm.dst, scope)[-1])
    assert dst_sym is c
    assert isinstance(stm.src, BinOp)
    assert stm.src.op == 'Add'
    assert isinstance(stm.src.left, Temp)
    left_sym = cast(Symbol, qualified_symbols(stm.src.left, scope)[-1])
    assert left_sym is a
    assert isinstance(stm.src.right, Temp)
    right_sym = cast(Symbol, qualified_symbols(stm.src.right, scope)[-1])
    assert right_sym is b

    assert not parser.parse_block_line()


def test_exp_temp():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('x')
    assert isinstance(exp, Temp)
    assert exp.name == 'x'
    assert exp.ctx == Ctx.LOAD


def test_exp_attr():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('x.y.z')
    assert isinstance(exp, Attr)
    assert exp.name == 'z'
    assert exp.exp.name == 'y'
    assert exp.exp.exp.name == 'x'


def test_exp_list():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope
    x = scope.add_sym('x', tags=set(), typ=Type.int())
    y = scope.add_sym('y', tags=set(), typ=Type.int())
    z = scope.add_sym('z', tags=set(), typ=Type.int())

    exp = parser.parse_exp('[x y z]')
    assert isinstance(exp, Array)
    array = cast(Array, exp)
    assert array.is_mutable
    assert len(array.items) == 3
    assert array.items[0].name == 'x'
    assert array.items[1].name == 'y'
    assert array.items[2].name == 'z'


def test_exp_tuple():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope
    x = scope.add_sym('x', tags=set(), typ=Type.int())
    y = scope.add_sym('y', tags=set(), typ=Type.int())
    z = scope.add_sym('z', tags=set(), typ=Type.int())

    exp = parser.parse_exp('(x y z)')
    assert isinstance(exp, Array)
    array = cast(Array, exp)
    assert array.is_mutable is False
    assert len(array.items) == 3
    assert array.items[0].name == 'x'
    assert array.items[1].name == 'y'
    assert array.items[2].name == 'z'


def test_exp_binop():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('(+ 123 _a.b)')
    assert isinstance(exp, BinOp)
    bin = cast(BinOp, exp)
    assert bin.op == 'Add'
    assert isinstance(bin.left, Const)
    assert bin.left.value == 123
    assert isinstance(bin.right, Attr)
    assert bin.right.name == 'b'
    assert bin.right.exp.name == '_a'


def test_exp_binop_2():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('(+ "123" \'456\')')
    assert isinstance(exp, BinOp)
    bin = cast(BinOp, exp)
    assert bin.op == 'Add'
    assert isinstance(bin.left, Const)
    assert bin.left.value == '123'
    assert isinstance(bin.right, Const)
    assert bin.right.value == '456'


def test_exp_relop():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('(== 123 _a.b)')
    assert isinstance(exp, RelOp)
    rel = cast(RelOp, exp)
    assert rel.op == 'Eq'
    assert isinstance(rel.left, Const)
    assert rel.left.value == 123
    assert isinstance(rel.right, Attr)
    assert rel.right.name == 'b'
    assert rel.right.exp.name == '_a'


def test_exp_mld():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('(mld xs 123)')
    assert isinstance(exp, MRef)
    mref = cast(MRef, exp)
    assert isinstance(mref.mem, Temp)
    assert mref.mem.name == 'xs'
    assert isinstance(mref.offset, Const)
    assert mref.offset.value == 123


def test_exp_mst():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('(mst xs 123 y)')
    assert isinstance(exp, MStore)
    mst = cast(MStore, exp)
    assert isinstance(mst.mem, Temp)
    assert mst.mem.name == 'xs'
    assert isinstance(mst.offset, Const)
    assert mst.offset.value == 123
    assert isinstance(mst.exp, Temp)
    assert mst.exp.name == 'y'


def test_exp_call():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('(call f (+ 1 2) _x y.z)')
    assert isinstance(exp, Call)
    call = cast(Call, exp)
    assert isinstance(call.func, Temp)
    assert call.func.name == 'f'
    assert call.func.ctx == Ctx.CALL
    assert len(call.args) == 3
    assert isinstance(call.args[0][1], BinOp)
    assert call.args[0][1].op == 'Add'
    assert isinstance(call.args[0][1].left, Const)
    assert isinstance(call.args[0][1].right, Const)
    assert isinstance(call.args[1][1], Temp)
    assert call.args[1][1].name == '_x'
    assert isinstance(call.args[2][1], Attr)
    assert call.args[2][1].name == 'z'
    assert call.args[2][1].exp.name == 'y'


def test_exp_new():
    setup_test()
    parser = IrReader('')
    
    exp = parser.parse_exp('(new C (+ 1 2) _x y.z)')
    assert isinstance(exp, New)
    call = cast(New, exp)
    assert isinstance(call.func, Temp)
    assert call.func.name == 'C'
    assert call.func.ctx == Ctx.CALL
    assert len(call.args) == 3
    assert isinstance(call.args[0][1], BinOp)
    assert call.args[0][1].op == 'Add'
    assert isinstance(call.args[0][1].left, Const)
    assert isinstance(call.args[0][1].right, Const)
    assert isinstance(call.args[1][1], Temp)
    assert call.args[1][1].name == '_x'
    assert isinstance(call.args[2][1], Attr)
    assert call.args[2][1].name == 'z'
    assert call.args[2][1].exp.name == 'y'


def test_exp_syscall():
    setup_test()
    parser = IrReader('')

    exp = parser.parse_exp('(syscall print 1 2 3)')
    assert isinstance(exp, SysCall)
    call = cast(SysCall, exp)
    assert call.name == 'print'
    assert len(call.args) == 3
    assert isinstance(call.args[0][1], Const)
    assert isinstance(call.args[1][1], Const)
    assert isinstance(call.args[2][1], Const)


def test_stm_cmv():
    setup_test()
    parser = IrReader('')

    stm = parser.parse_stm('mv? cond z (+ x y)')
    assert isinstance(stm, CMove)
    mv = cast(CMove, stm)
    assert isinstance(mv.cond, Temp)
    assert mv.dst == Temp('z', Ctx.STORE)
    assert isinstance(mv.src, BinOp)
    assert mv.src == BinOp('Add', Temp('x'), Temp('y'))


def test_stm_mv():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope
    xs = scope.add_sym('xs', tags=set(), typ=Type.list(Type.int(), 3))
    blk = Block(scope)
    parser.current_block = blk
    scope.set_entry_block(blk)

    stm = parser.parse_stm('mv xs [1 2 3]')
    assert isinstance(stm, Move)
    mv = cast(Move, stm)
    assert mv.dst == Temp('xs', Ctx.STORE)
    dst_sym = cast(Symbol, qualified_symbols(mv.dst, scope)[-1])
    assert dst_sym is xs
    assert isinstance(mv.src, Array)
    array = cast(Array, mv.src)
    assert array.items == [Const(1), Const(2), Const(3)]
    assert array.is_mutable


def test_stm_mv_call():
    setup_test()
    parser = IrReader('')

    stm = parser.parse_stm('mv v (call func 1 2 3)')
    assert isinstance(stm, Move)
    mv = cast(Move, stm)
    assert mv.dst == Temp('v', Ctx.STORE)
    assert isinstance(mv.src, Call)
    call = cast(Call, mv.src)
    assert call.func.name == 'func'
    assert call.args == [('', Const(1)), ('', Const(2)), ('', Const(3))]

def test_stm_mv_tuple():
    setup_test()
    parser = IrReader('')

    stm = parser.parse_stm('mv ((mld x 0) (mld y 0)) (call func)')
    assert isinstance(stm, Move)
    mv = cast(Move, stm)
    assert mv.dst == Array(
        [
            MRef(Temp('x'), Const(0), Ctx.LOAD),
            MRef(Temp('y'), Const(0), Ctx.LOAD),
        ], mutable=False)
    assert isinstance(mv.src, Call)
    call = cast(Call, mv.src)
    assert call.func.name == 'func'
    assert call.args == []


def test_stm_expr():
    setup_test()
    parser = IrReader('')

    stm = parser.parse_stm('expr (syscall print 1 2 3)')
    assert isinstance(stm, Expr)
    expr = cast(Expr, stm)
    assert expr.exp == SysCall(Temp('print'), [('', Const(1)), ('', Const(2)), ('', Const(3))], {})


def test_stm_j():
    setup_test()
    parser = IrReader('')
    top = env.scopes['@top']
    blk1 = Block(top)
    blk2 = Block(top)
    parser.blocks['blk1'] = blk1
    parser.blocks['blk2'] = blk2
    parser.current_block = blk1

    stm = parser.parse_stm('j blk2')
    assert isinstance(stm, Jump)
    jmp = cast(Jump, stm)
    assert jmp.target == blk2.bid


def test_stm_cj():
    setup_test()
    parser = IrReader('')
    top = env.scopes['@top']
    blk1 = Block(top)
    blk2 = Block(top)
    blk3 = Block(top)
    parser.blocks['blk1'] = blk1
    parser.blocks['blk2'] = blk2
    parser.blocks['blk3'] = blk3
    parser.current_block = blk1

    stm = parser.parse_stm('cj cond blk2 blk3')
    assert isinstance(stm, CJump)
    jmp = cast(CJump, stm)
    assert jmp.exp.name == 'cond'
    assert jmp.true == blk2.bid
    assert jmp.false == blk3.bid


def test_stm_mj():
    setup_test()
    parser = IrReader('')
    top = env.scopes['@top']
    blk1 = Block(top)
    blk2 = Block(top)
    blk3 = Block(top)
    blk4 = Block(top)
    parser.blocks['blk1'] = blk1
    parser.blocks['blk2'] = blk2
    parser.blocks['blk3'] = blk3
    parser.blocks['blk4'] = blk4
    parser.current_block = blk1

    stm = parser.parse_stm('mj c1 blk2 c2 blk3 c3 blk4')
    assert isinstance(stm, MCJump)
    jmp = cast(MCJump, stm)
    assert len(jmp.conds) == 3
    assert len(jmp.targets) == 3
    assert jmp.conds[0].name == 'c1'
    assert jmp.targets[0] == blk2.bid
    assert jmp.conds[1].name == 'c2'
    assert jmp.targets[1] == blk3.bid
    assert jmp.conds[2].name == 'c3'
    assert jmp.targets[2] == blk4.bid


def test_stm_phi():
    pass


def test_parse_operands_1():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope

    text = '(a b (c)) b (+ a b)'
    ops = parser.parse_operands(text)
    assert len(ops) == 3
    assert ops[0] == '(a b (c))'
    assert ops[1] == 'b'
    assert ops[2] == '(+ a b)'


def test_parse_operands_2():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope

    text = 'b.v  __d__ ( a b.v (_c_) )(== a b  )'
    ops = parser.parse_operands(text)
    assert len(ops) == 4
    assert ops[0] == 'b.v'
    assert ops[1] == '__d__'
    assert ops[2] == '(a b.v (_c_))'
    assert ops[3] == '(== a b)'
    

def test_cfg_1():
    setup_test()
    src = '''
    blk1:
    mv a 1
    j blk2

    blk2:
    mv b 2
    j blk3

    blk3:
    mv c (== a b)
    cj c blk4 blk5

    blk4:
    mv @return 0
    j exit

    blk5:
    mv @return 1
    j exit

    exit:
    ret @return
    '''
    parser = IrReader(src)
    scope = Scope.create(None, 'S', set(), 0)
    parser.current_scope = scope
    a = scope.add_sym('a', tags=set(), typ=Type.int(8))
    b = scope.add_sym('b', tags=set(), typ=Type.int(8))
    c = scope.add_sym('c', tags=set(), typ=Type.bool())
    ret = scope.add_sym('ret', tags=set(), typ=Type.int(8))

    parser.parse_all_blocks()

    blks = scope.traverse_blocks()
    blk1 = next(blks)
    blk2 = next(blks)
    blk3 = next(blks)
    blk4 = next(blks)
    exit6 = next(blks)
    blk5 = next(blks)
    with pytest.raises(StopIteration) as e:
        next(blks)
    assert len(blk1.succs) == 1
    assert blk1.succs[0] is blk2
    assert len(blk2.succs) == 1
    assert blk2.succs[0] is blk3
    assert len(blk3.succs) == 2
    assert blk3.succs[0] is blk4
    assert blk3.succs[1] is blk5
    assert len(blk4.succs) == 1
    assert blk4.succs[0] is exit6
    assert len(blk5.succs) == 1
    assert blk5.succs[0] is exit6
    assert not exit6.succs

    assert not blk1.preds
    assert len(blk2.preds) == 1
    assert blk2.preds[0] is blk1
    assert len(blk3.preds) == 1
    assert blk3.preds[0] is blk2
    assert len(blk4.preds) == 1
    assert blk4.preds[0] is blk3
    assert len(blk5.preds) == 1
    assert blk5.preds[0] is blk3
    assert len(exit6.preds) == 2
    assert exit6.preds[0] is blk4
    assert exit6.preds[1] is blk5


def test_scope_head_1():
    setup_test()
    src = '''
scope AFunction
tags  function
param  a:int32
param   b:int32
return  int64
var c: int16
var d :int16
var e : bit256
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['AFunction']
    assert scope.name == 'AFunction'
    assert scope.is_function()
    assert scope.has_sym('a')
    assert scope.has_sym('b')
    assert scope.has_sym('c')
    assert scope.has_sym('d')
    assert scope.has_sym('e')
    assert scope.has_sym(Symbol.return_name)

    a = scope.symbols['a']
    b = scope.symbols['b']
    c = scope.symbols['c']
    d = scope.symbols['d']
    e = scope.symbols['e']
    ret = scope.symbols[Symbol.return_name]
    assert a.typ.is_int()
    assert a.typ.width == 32
    assert a.typ.signed is True
    assert b.typ.is_int()
    assert b.typ.width == 32
    assert b.typ.signed is True
    assert c.typ.is_int()
    assert c.typ.width == 16
    assert c.typ.signed is True
    assert d.typ.is_int()
    assert d.typ.width == 16
    assert d.typ.signed is True
    assert e.typ.is_int()
    assert e.typ.signed is False
    assert e.typ.width == 256
    assert ret.typ.is_int()
    assert ret.typ.width == 64


def test_scope_head_2():
    setup_test()
    src = '''
scope S
tags function
param a: int8 { free }
var x0 : int16
var x1 : int16 { }
var x2 : object(__builtin__.int) { temp }
var x3 : list<int32>[10] { temp temp free }
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['S']
    assert scope.has_sym('@in_a')
    assert scope.has_sym('a')
    assert scope.has_sym('x0')
    assert scope.has_sym('x1')
    assert scope.has_sym('x2')
    assert scope.has_sym('x3')

    a = scope.symbols['a']
    assert a.typ.is_int()
    assert a.typ.width == 8
    assert a.typ.signed is True
    assert len(a.tags) == 1
    assert 'free' in a.tags

    x0 = scope.symbols['x0']
    assert x0.typ.is_int()
    assert x0.typ.width == 16
    assert x0.typ.signed is True
    assert len(x0.tags) == 0
    x1 = scope.symbols['x1']
    assert x1.typ.is_int()
    assert x1.typ.width == 16
    assert x1.typ.signed is True
    assert len(x1.tags) == 0
    x2 = scope.symbols['x2']
    assert x2.typ.is_object()
    assert len(x2.tags) == 1
    assert 'temp' in x2.tags
    x3 = scope.symbols['x3']
    assert x3.typ.is_list()
    assert len(x3.tags) == 2
    assert 'temp' in x3.tags
    assert 'free' in x3.tags


def test_scope_head_3():
    setup_test()
    src = '''
scope C
tags class

scope C.D
tags class

scope C.D.E

tags method

'''
    parser = IrReader(src)
    parser.parse_scope()
    C = env.scopes['C']
    D = env.scopes['C.D']
    E = env.scopes['C.D.E']

    assert C.name == 'C'
    assert C.is_class()
    assert D.name == 'C.D'
    assert D.base_name == 'D'
    assert D.parent is C
    assert D.is_class()
    assert E.name == 'C.D.E'
    assert E.base_name == 'E'
    assert E.parent is D
    assert E.is_method()


def test_scope_import_var():
    setup_test()
    src = '''
scope C
tags namespace
from D import x

scope D
tags namespace
var x: int32
'''
    parser = IrReader(src)
    parser.parse_scope()
    C = env.scopes['C']
    D = env.scopes['D']

    x_in_C = C.find_sym('x')
    x_in_D = D.find_sym('x')
    assert x_in_C and x_in_D
    assert x_in_C is x_in_D
    assert x_in_C.scope is D
    assert x_in_C.is_imported()
    assert C.find_owner_scope(x_in_C) is C


def test_scope_1():
    setup_test()
    src = '''
scope @top.C
tags  class
var __init__: function(@top.C.__init__)
var x: int32

scope @top.C.__init__
tags  method ctor
param  self:object(@top.C)
param  x:int32
return object(@top.C)

blk1:
mv x @in_x
mv self.x x

scope @top.caller_func
tags  function_module function
return int32
var c0: object(@top.C)
var x: int32

blk1:
mv x 10
mv c0 (new C x)
mv @return c0.x
ret @return
'''
    top = env.scopes['@top']
    
    parser = IrReader(src)
    parser.parse_scope()

    # top_C = top.find_sym('C')
    # top_caller_func = top.find_sym('caller_func')
    # assert top_C
    # assert top_C.typ.is_class()
    # assert top_caller_func
    # assert top_caller_func.typ.is_function()

    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('caller_func', tags=set(), typ=Type.function('@top.caller_func'))
    
    C = env.scopes['@top.C']
    C_ctor = env.scopes['@top.C.__init__']
    assert C.is_class()
    assert C.has_sym('__init__')
    assert C.entry_block
    assert C.exit_block
    C_ctor_sym = C.find_sym('__init__')
    assert C_ctor_sym.typ.is_function()
    assert C_ctor_sym.typ.scope is C_ctor

    assert C.has_sym('x')
    C_x_sym = C.find_sym('x')
    assert C_x_sym.typ.is_int()

    gen = C_ctor.traverse_blocks()
    blk1 = next(gen)
    assert C_ctor.entry_block is blk1
    assert C_ctor.exit_block is blk1

    caller_func = env.scopes['@top.caller_func']
    print(caller_func)
    assert caller_func.has_sym('c0')
    caller_func_c0_sym = caller_func.find_sym('c0')
    assert caller_func_c0_sym.typ.is_object()
    assert caller_func_c0_sym.typ.scope is C

    gen = caller_func.traverse_blocks()
    blk1 = next(gen)
    assert caller_func.entry_block is blk1
    assert caller_func.exit_block is blk1


def test_irreader_creates_function_scope():
    setup_test()
    parser = IrReader("scope @top.f\ntags function\nvar x: int32\n\nblk1:\nmv x 0\n")
    parser.parse_scope()
    assert isinstance(env.scopes['@top.f'], FunctionScope)


def test_irreader_creates_class_scope():
    setup_test()
    parser = IrReader("scope @top.C\ntags class\n")
    parser.parse_scope()
    assert isinstance(env.scopes['@top.C'], ClassScope)


def test_irreader_creates_namespace_scope():
    setup_test()
    parser = IrReader("scope mypkg\ntags namespace\n")
    parser.parse_scope()
    assert isinstance(env.scopes['mypkg'], NamespaceScope)


# ============================================================
# Phi / UPhi / LPhi parsing
# ============================================================

def test_phi_basic():
    """Parse phi with args and no ps."""
    setup_test()
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
mv x 1
j exit

blk3:
mv x 2
j exit

exit:
phi x (1 2)
mv @return x
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['F']
    exit_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'exit':
            exit_blk = blk
            break
    assert exit_blk is not None
    phi_stm = exit_blk.stms[0]
    assert isinstance(phi_stm, Phi)
    assert phi_stm.var.name == 'x'
    assert len(phi_stm.args) == 2
    assert isinstance(phi_stm.args[0], Const) and phi_stm.args[0].value == 1
    assert isinstance(phi_stm.args[1], Const) and phi_stm.args[1].value == 2
    assert len(phi_stm.ps) == 0


def test_phi_with_ps():
    """Parse phi with args and path predicates."""
    setup_test()
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
mv x 1
j exit

blk3:
mv x 2
j exit

exit:
phi x (1 2) (c True)
mv @return x
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['F']
    exit_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'exit':
            exit_blk = blk
            break
    assert exit_blk is not None
    phi_stm = exit_blk.stms[0]
    assert isinstance(phi_stm, Phi)
    assert len(phi_stm.args) == 2
    assert len(phi_stm.ps) == 2


def test_uphi_parse():
    """Parse uphi statement."""
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
uphi x (1 2)
mv @return x
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['F']
    phi_stm = scope.entry_block.stms[0]
    assert isinstance(phi_stm, UPhi)
    assert phi_stm.var.name == 'x'
    assert len(phi_stm.args) == 2


def test_lphi_parse():
    """Parse lphi statement."""
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
lphi x (1 2)
mv @return x
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['F']
    phi_stm = scope.entry_block.stms[0]
    assert isinstance(phi_stm, LPhi)
    assert phi_stm.var.name == 'x'
    assert len(phi_stm.args) == 2


def test_phi_with_var_args():
    """Parse phi with variable arguments."""
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var x: int32
var a: int32
var b: int32

blk1:
phi x (a b)
mv @return x
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['F']
    phi_stm = scope.entry_block.stms[0]
    assert isinstance(phi_stm, Phi)
    assert len(phi_stm.args) == 2
    assert isinstance(phi_stm.args[0], Temp)
    assert phi_stm.args[0].name == 'a'
    assert isinstance(phi_stm.args[1], Temp)
    assert phi_stm.args[1].name == 'b'


# ============================================================
# Coverage: check_int, is_binop, is_relop, ir_stm, parse_scalar fallback
# ============================================================

def test_parse_scalar_fallback():
    """parse_scalar with unrecognized token returns Const(str)."""
    setup_test()
    parser = IrReader('')
    result = parser.parse_scalar('3.14')
    assert isinstance(result, Const)
    assert result.value == '3.14'


def test_ir_stm_utility():
    """ir_stm() helper creates a statement from code string."""
    from polyphony.compiler.ir.irreader import ir_stm
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    scope.add_sym('a', tags=set(), typ=Type.int(32))
    stm = ir_stm(scope, 'mv a 1')
    assert isinstance(stm, Move)
    assert stm.dst.name == 'a'
    assert stm.src.value == 1


# ============================================================
# Coverage: parse_early_scope_head, _type_from_scope_tags
# ============================================================

def test_parse_early_scope_head():
    setup_test()
    src = '''scope F
tags function
'''
    parser = IrReader(src)
    parser.parse_early_scope_head()
    assert 'F' in env.scopes
    scope = env.scopes['F']
    assert scope.is_function()


def test_parse_early_scope_head_nested():
    setup_test()
    src = '''scope @top.C
tags class
'''
    parser = IrReader(src)
    parser.parse_early_scope_head()
    assert '@top.C' in env.scopes
    scope = env.scopes['@top.C']
    assert scope.is_class()


def test_type_from_scope_tags_namespace():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'NS', {'namespace'}, 0)
    typ = parser._type_from_scope_tags(scope, {'namespace'})
    assert typ.is_namespace()


def test_type_from_scope_tags_method():
    setup_test()
    parser = IrReader('')
    scope = Scope.create(None, 'M', {'method'}, 0)
    typ = parser._type_from_scope_tags(scope, {'method'})
    assert typ.is_function()


# ============================================================
# Coverage: closure free variable detection
# ============================================================

def test_parse_var_closure_free():
    """parse_var detects free variables in closure scope."""
    setup_test()
    outer = Scope.create(None, 'outer', {'function', 'enclosure'}, 0)
    x_sym = outer.add_sym('x', tags=set(), typ=Type.int(32))

    inner = Scope.create(outer, 'inner', {'function', 'closure'}, 0)
    inner.import_sym(x_sym, 'x')

    parser = IrReader('')
    parser.current_scope = inner
    var = parser.parse_var('x', Ctx.LOAD)
    assert isinstance(var, Temp)
    assert var.name == 'x'
    # x should be tagged as 'free' since it belongs to the enclosure
    assert 'free' in x_sym.tags


# ============================================================
# CondOp / PolyOp / MStm parsing
# ============================================================

def test_exp_condop():
    setup_test()
    parser = IrReader('')

    exp = parser.parse_exp('(? c 1 2)')
    assert isinstance(exp, CondOp)
    assert isinstance(exp.cond, Temp)
    assert exp.cond.name == 'c'
    assert isinstance(exp.left, Const)
    assert exp.left.value == 1
    assert isinstance(exp.right, Const)
    assert exp.right.value == 2


def test_exp_condop_nested():
    setup_test()
    parser = IrReader('')

    exp = parser.parse_exp('(? (== x 0) (+ a b) 0)')
    assert isinstance(exp, CondOp)
    assert isinstance(exp.cond, RelOp)
    assert exp.cond.op == 'Eq'
    assert isinstance(exp.left, BinOp)
    assert exp.left.op == 'Add'
    assert isinstance(exp.right, Const)
    assert exp.right.value == 0


def test_exp_polyop():
    setup_test()
    parser = IrReader('')

    exp = parser.parse_exp('(+ [a b c])')
    assert isinstance(exp, PolyOp)
    assert exp.op == 'Add'
    assert len(exp.values) == 3
    assert isinstance(exp.values[0], Temp)
    assert exp.values[0].name == 'a'
    assert isinstance(exp.values[1], Temp)
    assert exp.values[1].name == 'b'
    assert isinstance(exp.values[2], Temp)
    assert exp.values[2].name == 'c'


def test_exp_polyop_mult():
    setup_test()
    parser = IrReader('')

    exp = parser.parse_exp('(* [1 2 3 4])')
    assert isinstance(exp, PolyOp)
    assert exp.op == 'Mult'
    assert len(exp.values) == 4
    assert all(isinstance(v, Const) for v in exp.values)
    assert [v.value for v in exp.values] == [1, 2, 3, 4]


def test_stm_mstm():
    setup_test()
    src = '''
scope F
tags function
var a: int32
var b: int32

blk1:
mstm
| mv a b
| mv b a
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = env.scopes['F']

    blk1 = scope.entry_block
    mstm = blk1.stms[0]
    assert isinstance(mstm, MStm)
    assert len(mstm.stms) == 2
    assert isinstance(mstm.stms[0], Move)
    mv0 = cast(Move, mstm.stms[0])
    assert mv0.dst.name == 'a'
    assert mv0.src.name == 'b'
    assert isinstance(mstm.stms[1], Move)
    mv1 = cast(Move, mstm.stms[1])
    assert mv1.dst.name == 'b'
    assert mv1.src.name == 'a'


# ============================================================
# ExprType parsing
# ============================================================

def test_parse_type_expr():
    setup_test()
    top = env.scopes['@top']
    F = Scope.create(top, 'F', {'function'}, 0)
    parser = IrReader('')

    t = parser.parse_type('expr(@top.F, x)')
    assert t.is_expr()
    assert t.scope_name == '@top.F'
    assert isinstance(t.expr, Expr)
    assert isinstance(t.expr.exp, Temp)
    assert t.expr.exp.name == 'x'


def test_parse_type_expr_binop():
    setup_test()
    top = env.scopes['@top']
    F = Scope.create(top, 'F', {'function'}, 0)
    parser = IrReader('')

    t = parser.parse_type('expr(@top.F, (+ a 1))')
    assert t.is_expr()
    assert t.scope_name == '@top.F'
    assert isinstance(t.expr.exp, BinOp)
    assert t.expr.exp.op == 'Add'


def test_parse_type_port():
    setup_test()
    top = env.scopes['@top']
    M = Scope.create(top, 'M', {'class'}, 0)
    ctor = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    p_sym = ctor.add_sym('p', tags=set(), typ=Type.int(32))
    parser = IrReader('')

    t = parser.parse_type('port(@top.M, int32, output, 0, False, @top.M.__init__:p)')
    assert t.is_port()
    assert t.scope_name == '@top.M'
    assert t.dtype == Type.int(32)
    assert t.direction == 'output'
    assert t.init == 0
    assert t.assigned is False
    assert t.root_symbol is p_sym


def test_parse_type_port_input():
    setup_test()
    top = env.scopes['@top']
    M = Scope.create(top, 'M', {'class'}, 0)
    ctor = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    q_sym = ctor.add_sym('q', tags=set(), typ=Type.int(8))
    parser = IrReader('')

    t = parser.parse_type('port(@top.M, int8, input, 42, True, @top.M.__init__:q)')
    assert t.is_port()
    assert t.dtype == Type.int(8)
    assert t.direction == 'input'
    assert t.init == 42
    assert t.assigned is True
    assert t.root_symbol is q_sym


def test_parse_type_port_lazy_resolution():
    """root_symbol is resolved lazily, so Symbol can be registered after PortType creation."""
    setup_test()
    top = env.scopes['@top']
    M = Scope.create(top, 'M', {'class'}, 0)
    ctor = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    # Do NOT add symbol yet — simulate parse order issue
    parser = IrReader('')

    t = parser.parse_type('port(@top.M, int32, output, 0, False, @top.M.__init__:p)')
    assert t.is_port()

    # Now add the symbol after PortType was created
    p_sym = ctor.add_sym('p', tags=set(), typ=Type.int(32))

    # Lazy resolution should find it
    assert t.root_symbol is p_sym
