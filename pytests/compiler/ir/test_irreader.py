from collections import deque
from typing import cast
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irhelper import qualified_symbols
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test
import pytest


def test_type_1():
    setup_test()
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
    p = parser.parse_scalar('True')
    assert p == Const(True)

    p = parser.parse_scalar('False')
    assert p == Const(False)


def test_var_7():
    setup_test()
    parser = IRParser('')
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
    parser = IRParser(src)
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
    parser = IRParser('')
    
    exp = parser.parse_exp('x')
    assert isinstance(exp, Temp)
    assert exp.name == 'x'
    assert exp.ctx == Ctx.LOAD


def test_exp_attr():
    setup_test()
    parser = IRParser('')
    
    exp = parser.parse_exp('x.y.z')
    assert isinstance(exp, Attr)
    assert exp.name == 'z'
    assert exp.exp.name == 'y'
    assert exp.exp.exp.name == 'x'


def test_exp_list():
    setup_test()
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser('')
    
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
    parser = IRParser('')
    
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
    parser = IRParser('')
    
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
    parser = IRParser('')
    
    exp = parser.parse_exp('(mld xs 123)')
    assert isinstance(exp, MRef)
    mref = cast(MRef, exp)
    assert isinstance(mref.mem, Temp)
    assert mref.mem.name == 'xs'
    assert isinstance(mref.offset, Const)
    assert mref.offset.value == 123


def test_exp_mst():
    setup_test()
    parser = IRParser('')
    
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
    parser = IRParser('')
    
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
    parser = IRParser('')
    
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
    parser = IRParser('')

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
    parser = IRParser('')

    stm = parser.parse_stm('mv? cond z (+ x y)')
    assert isinstance(stm, CMove)
    mv = cast(CMove, stm)
    assert isinstance(mv.cond, Temp)
    assert mv.dst == Temp('z', Ctx.STORE)
    assert isinstance(mv.src, BinOp)
    assert mv.src == BinOp('Add', Temp('x'), Temp('y'))


def test_stm_mv():
    setup_test()
    parser = IRParser('')
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
    parser = IRParser('')

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
    parser = IRParser('')

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
    parser = IRParser('')

    stm = parser.parse_stm('expr (syscall print 1 2 3)')
    assert isinstance(stm, Expr)
    expr = cast(Expr, stm)
    assert expr.exp == SysCall(Temp('print'), [('', Const(1)), ('', Const(2)), ('', Const(3))], {})


def test_stm_j():
    setup_test()
    parser = IRParser('')
    top = env.scopes['@top']
    blk1 = Block(top)
    blk2 = Block(top)
    parser.blocks['blk1'] = blk1
    parser.blocks['blk2'] = blk2
    parser.current_block = blk1

    stm = parser.parse_stm('j blk2')
    assert isinstance(stm, Jump)
    jmp = cast(Jump, stm)
    assert jmp.target.name == blk2.name


def test_stm_cj():
    setup_test()
    parser = IRParser('')
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
    assert jmp.true.name == blk2.name
    assert jmp.false.name == blk3.name


def test_stm_mj():
    setup_test()
    parser = IRParser('')
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
    assert jmp.targets[0].name == blk2.name
    assert jmp.conds[1].name == 'c2'
    assert jmp.targets[1].name == blk3.name
    assert jmp.conds[2].name == 'c3'
    assert jmp.targets[2].name == blk4.name


def test_stm_phi():
    pass


def test_parse_operands_1():
    setup_test()
    parser = IRParser('')
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
    parser = IRParser('')
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
    parser = IRParser(src)
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
    parser = IRParser(src)
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
    parser = IRParser(src)
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
    parser = IRParser(src)
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
    parser = IRParser(src)
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
    
    parser = IRParser(src)
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
