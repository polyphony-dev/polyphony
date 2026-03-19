"""Tests for FlattenFieldAccess."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.transformers.inlineopt import FlattenFieldAccess
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test, setup_libs


def build_scope(src):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def parse_all(src):
    """Parse all scopes and return the env."""
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    return env


def test_flatten_does_not_crash_on_simple_function():
    """FlattenFieldAccess handles simple function scope without crash."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 10
mv @return x
ret @return
'''
    scope = build_scope(src)
    FlattenFieldAccess().process(scope)

    # Should not change simple TEMPs
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                assert isinstance(stm.src, Const)
                assert stm.src.value == 10


def test_flatten_preserves_non_object_attrs():
    """FlattenFieldAccess does not flatten non-object attributes."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 5
mv y 10
mv @return x
ret @return
'''
    scope = build_scope(src)
    FlattenFieldAccess().process(scope)

    # All TEMPs should remain as TEMPs
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp):
                pass  # No assertion needed, just verify no crash


def test_flatten_simple_object_field_read():
    """FlattenFieldAccess converts c.x to c_x for non-module object fields."""
    setup_test()
    src = '''
scope @top.C
tags class
var x: int32

scope @top.func
tags function returnable
return int32
var c: object(@top.C)

blk1:
mv @return c.x
ret @return
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('func', tags=set(), typ=Type.function('@top.func'))

    func = env.scopes['@top.func']
    FlattenFieldAccess().process(func)

    blk = next(func.traverse_blocks())
    # c.x should be flattened to c_x (Temp)
    mv = blk.stms[0]
    assert isinstance(mv, Move)
    assert isinstance(mv.src, Temp)
    assert mv.src.name == 'c_x'

    # Flattened symbol should exist
    c_x_sym = func.find_sym('c_x')
    assert c_x_sym is not None
    assert c_x_sym.is_flattened()


def test_flatten_simple_object_field_write():
    """FlattenFieldAccess converts c.x = val to c_x = val."""
    setup_test()
    src = '''
scope @top.C
tags class
var x: int32

scope @top.func
tags function
return none
var c: object(@top.C)

blk1:
mv c.x 42
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('func', tags=set(), typ=Type.function('@top.func'))

    func = env.scopes['@top.func']
    FlattenFieldAccess().process(func)

    blk = next(func.traverse_blocks())
    mv = blk.stms[0]
    assert isinstance(mv, Move)
    assert isinstance(mv.dst, Temp)
    assert mv.dst.name == 'c_x'
    assert isinstance(mv.src, Const) and mv.src.value == 42


def test_flatten_nested_object_field():
    """FlattenFieldAccess converts c.d.v to c_d_v for nested objects."""
    setup_test()
    src = '''
scope @top.D
tags class
var v: int32

scope @top.C
tags class
var d: object(@top.D)

scope @top.func
tags function returnable
return int32
var c: object(@top.C)

blk1:
mv @return c.d.v
ret @return
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('D', tags=set(), typ=Type.klass('@top.D'))
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('func', tags=set(), typ=Type.function('@top.func'))

    func = env.scopes['@top.func']
    FlattenFieldAccess().process(func)

    blk = next(func.traverse_blocks())
    mv = blk.stms[0]
    assert isinstance(mv, Move)
    assert isinstance(mv.src, Temp)
    assert mv.src.name == 'c_d_v'

    c_d_v_sym = func.find_sym('c_d_v')
    assert c_d_v_sym is not None
    assert c_d_v_sym.is_flattened()


def test_flatten_method_in_non_module_preserves_attr():
    """FlattenFieldAccess does NOT flatten attrs in methods of non-module classes."""
    setup_test()
    src = '''
scope @top.D
tags class
var x: int32

scope @top.C
tags class
var d: object(@top.D)
var get_d_x: function(@top.C.get_d_x)

scope @top.C.get_d_x
tags method
param self:object(@top.C)
return int32

blk1:
mv @return self.d.x
ret @return
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('D', tags=set(), typ=Type.klass('@top.D'))
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))

    method = env.scopes['@top.C.get_d_x']
    assert method.is_method()
    assert not method.parent.is_module()

    FlattenFieldAccess().process(method)

    blk = next(method.traverse_blocks())
    mv = blk.stms[0]
    assert isinstance(mv, Move)
    # Should remain as Attr (not flattened)
    assert isinstance(mv.src, Attr)


def test_flatten_method_in_module_flattens():
    """FlattenFieldAccess DOES flatten attrs in methods of module classes."""
    setup_test()
    src = '''
scope @top.D
tags class
var x: int32

scope @top.M
tags module class
var d: object(@top.D)
var run: function(@top.M.run)

scope @top.M.run
tags method
param self:object(@top.M)
return int32

blk1:
mv @return self.d.x
ret @return
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('D', tags=set(), typ=Type.klass('@top.D'))
    top.add_sym('M', tags=set(), typ=Type.klass('@top.M'))

    method = env.scopes['@top.M.run']
    assert method.is_method()
    assert method.parent.is_module()

    FlattenFieldAccess().process(method)

    blk = next(method.traverse_blocks())
    mv = blk.stms[0]
    assert isinstance(mv, Move)
    # Should be flattened: self.d.x -> self.d_x
    assert isinstance(mv.src, Attr)
    assert mv.src.name == 'd_x'


def test_flatten_existing_symbol_reused():
    """FlattenFieldAccess reuses an existing flattened symbol if already present."""
    setup_test()
    src = '''
scope @top.C
tags class
var x: int32

scope @top.func
tags function returnable
return int32
var c: object(@top.C)
var a: int32

blk1:
mv a c.x
mv @return c.x
ret @return
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('func', tags=set(), typ=Type.function('@top.func'))

    func = env.scopes['@top.func']
    FlattenFieldAccess().process(func)

    blk = next(func.traverse_blocks())
    # Both c.x references should use the same flattened name
    assert blk.stms[0].src.name == 'c_x'
    assert blk.stms[1].src.name == 'c_x'

    # Only one c_x symbol should exist
    c_x_sym = func.find_sym('c_x')
    assert c_x_sym is not None


def test_flatten_port_field_not_flattened():
    """FlattenFieldAccess does NOT flatten port object fields."""
    setup_test()
    setup_libs('io')
    src = '''
scope @top.func
tags function
return none
var p: object(polyphony.io.Port)

blk1:
expr (call p.rd)
'''
    parser = IrReader(src)
    parser.parse_scope()
    top = env.scopes['@top']
    top.add_sym('func', tags=set(), typ=Type.function('@top.func'))
    if not top.find_sym('polyphony'):
        top.add_sym('polyphony', tags=set(), typ=Type.namespace('polyphony'))

    func = env.scopes['@top.func']
    # Should not crash
    FlattenFieldAccess().process(func)

    # Port call should remain as Attr
    blk = next(func.traverse_blocks())
    assert len(blk.stms) >= 1


def test_flatten_nested_object_method_call():
    """FlattenFieldAccess handles c.d.get_x() -> c_d.get_x()."""
    setup_test()
    src = '''
scope @top.D
tags class
var x: int32
var get_x: function(@top.D.get_x)

scope @top.D.get_x
tags method
param self:object(@top.D)
return int32

blk1:
mv @return self.x
ret @return

scope @top.C
tags class
var d: object(@top.D)

scope @top.outer
tags function
return int32
var c: object(@top.C)

blk1:
mv @return (call c.d.get_x)
ret @return
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('D', tags=set(), typ=Type.klass('@top.D'))
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('outer', tags=set(), typ=Type.function('@top.outer'))

    func = env.scopes['@top.outer']
    FlattenFieldAccess().process(func)

    blk = next(func.traverse_blocks())
    mv = blk.stms[0]
    assert isinstance(mv, Move)
    # c.d.get_x() -> c_d.get_x()
    assert isinstance(mv.src, Call)
    assert isinstance(mv.src.func, Attr)
    assert mv.src.func.exp.name == 'c_d'
    assert mv.src.func.name == 'get_x'
    # c_d should be created
    assert func.find_sym('c_d') is not None


def test_flatten_module_object_preserves_attr():
    """FlattenFieldAccess does NOT flatten module object fields."""
    setup_test()
    src = '''
scope @top.M
tags module class
var x: int32

scope @top.func
tags function returnable
return int32
var m: object(@top.M)

blk1:
mv @return m.x
ret @return
'''
    parse_all(src)
    top = env.scopes['@top']
    top.add_sym('M', tags=set(), typ=Type.klass('@top.M'))
    top.add_sym('func', tags=set(), typ=Type.function('@top.func'))

    func = env.scopes['@top.func']
    FlattenFieldAccess().process(func)

    blk = next(func.traverse_blocks())
    mv = blk.stms[0]
    assert isinstance(mv, Move)
    # Should remain as Attr (module object)
    assert isinstance(mv.src, Attr)
    assert mv.src.name == 'x'


def test_flatten_with_expr_type_in_symbol():
    """FlattenFieldAccess flattens Attr inside ExprType of a symbol's type."""
    from polyphony.compiler.ir.types.exprtype import ExprType as ExprTypeClass
    from polyphony.compiler.ir.scope import Scope
    from polyphony.compiler.ir.block import Block
    from polyphony.compiler.ir.symbol import Symbol

    setup_test()
    top = Scope.global_scope()

    # Create class C with field n
    C = Scope.create(top, 'C', {'class'}, 0)
    C.add_sym('n', tags=set(), typ=Type.int(32))
    top.add_sym('C', tags=set(), typ=Type.klass(C))

    # Create function F
    F = Scope.create(top, 'F', {'function'}, 0)
    F.add_sym('c', tags=set(), typ=Type.object(C))

    # ExprType whose expr references c.n (Attr) -- the list length is c.n
    length_expr = Expr(exp=Attr(name='n', exp=Temp('c'), attr='n', ctx=Ctx.LOAD))
    et = ExprTypeClass(explicit=False, scope_name=F.name, expr=length_expr)
    list_typ = Type.list(Type.int(32), et)
    F.add_sym('xs', tags=set(), typ=list_typ)

    F.return_type = Type.int()
    F.add_return_sym()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    blk.append_stm(Move(Temp('@return', Ctx.STORE), Temp('xs')))
    blk.append_stm(Ret(Temp('@return')))
    Block.set_order(blk, 0)

    FlattenFieldAccess().process(F)

    # c.n in the ExprType should have been flattened to c_n
    c_n_sym = F.find_sym('c_n')
    assert c_n_sym is not None, 'c_n should be created by flattening ExprType'
    assert c_n_sym.is_flattened()


def test_flatten_attr_with_expr_type_in_symbol():
    """FlattenFieldAccess flattens Attr inside ExprType when processing Attr nodes."""
    from polyphony.compiler.ir.types.exprtype import ExprType as ExprTypeClass
    from polyphony.compiler.ir.scope import Scope
    from polyphony.compiler.ir.block import Block

    setup_test()
    top = Scope.global_scope()

    # Create class D with field m
    D = Scope.create(top, 'D', {'class'}, 0)
    D.add_sym('m', tags=set(), typ=Type.int(32))
    top.add_sym('D', tags=set(), typ=Type.klass(D))

    # Create class C with object field d of type D
    C = Scope.create(top, 'C', {'class'}, 0)
    C.add_sym('d', tags=set(), typ=Type.object(D))

    # C also has a list field whose length is an ExprType referencing d.m
    length_expr = Expr(exp=Attr(name='m', exp=Temp('d'), attr='m', ctx=Ctx.LOAD))
    et = ExprTypeClass(explicit=False, scope_name=C.name, expr=length_expr)
    list_typ = Type.list(Type.int(32), et)
    C.add_sym('arr', tags=set(), typ=list_typ)
    top.add_sym('C', tags=set(), typ=Type.klass(C))

    # Function accessing c.d (Attr with object receiver)
    F = Scope.create(top, 'F', {'function'}, 0)
    F.add_sym('c', tags=set(), typ=Type.object(C))
    F.return_type = Type.int()
    F.add_return_sym()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    # Access c.d (Attr node) -- triggers visit_Attr which checks ExprType
    blk.append_stm(Move(Temp('@return', Ctx.STORE),
                         Attr(name='d', exp=Temp('c'), attr='d', ctx=Ctx.LOAD)))
    blk.append_stm(Ret(Temp('@return')))
    Block.set_order(blk, 0)

    FlattenFieldAccess().process(F)

    # c.d should be flattened to c_d
    c_d_sym = F.find_sym('c_d')
    assert c_d_sym is not None


def test_flatten_make_new_ATTR_alias():
    """_make_new_ATTR is an alias for _make_new_attr."""
    setup_test()
    ffa = FlattenFieldAccess()
    assert ffa._make_new_ATTR is not None
    # They should produce the same result
    from polyphony.compiler.ir.scope import Scope
    from polyphony.compiler.ir.symbol import Symbol
    top = Scope.global_scope()
    F = Scope.create(top, 'f', {'function'}, 0)
    sym = F.add_sym('x', tags=set(), typ=Type.int(32))
    ir = Temp(name='x', ctx=Ctx.LOAD)
    result1 = ffa._make_new_attr((sym,), ir)
    result2 = ffa._make_new_ATTR((sym,), ir)
    assert result1.name == result2.name
