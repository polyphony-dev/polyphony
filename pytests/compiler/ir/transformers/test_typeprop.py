from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import name2var as _v
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.irreader import IRReader as IRParser, ir_stm
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.transformers.typeprop import TypePropagation
from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.builtin import builtin_symbols
from pytests.compiler.base import setup_test, install_builtins
import pytest

def test_specialize_func():
    setup_test(with_global=False)
    '''
    --- main ---
    from other import func_x

    def func(x):
        return func_x(x)

    func(1)

    --- other ---
    def func_x(x):
        return x + 1
    '''

    block_src = """
    scope @top
        tags namespace
        var other: namespace(other)
        var func: function(@top.func)
        from other import func_x
    blk1:
        expr (call func 1)

    scope @top.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (call func_x x)
        ret @return

    scope other
        tags namespace
        var func_x: function(other.func_x)

    scope other.func_x
        tags function
        param x: undef
        return int32
    blk1:
        mv x @in_x
        mv @return (+ x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()

    func = env.scopes['@top.func']
    func_i32 = env.scopes['@top.func_i32']
    other = env.scopes['other']
    func_x_i32 = env.scopes['other.func_x_i32']
    func_x_i32_sym = top.find_sym('func_x_i32')
    assert func_x_i32_sym
    assert func_x_i32_sym.scope is other
    assert func_x_i32_sym.typ.is_function()
    assert func_x_i32_sym.typ.scope is func_x_i32
    assert func_x_i32.is_specialized()

    assert func_x_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert func_x_i32.return_type == Type.int(width=32)

    func_i32_sym = top.find_sym('func_i32')
    assert func_i32_sym
    assert func_i32_sym.scope is top
    assert func_i32_sym.typ.is_function()
    assert func_i32_sym.typ.scope is func_i32
    assert func_i32.is_specialized()

    assert func_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert func_i32.return_type == Type.int(width=32)


def test_specialize_func_2():
    setup_test(with_global=False)
    '''
    --- main ---
    import other

    def func(x):
        return x + 1

    func(1)
    other.func(1)

    --- other ---
    def func(x):
        return x + 2
    '''

    block_src = """
    scope @top
        tags namespace
        var other: namespace(other)
        var func: function(@top.func)
    blk1:
        expr (call func 1)
        expr (call other.func 1)

    scope @top.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 1)
        ret @return

    scope other
        tags namespace
        var func: function(other.func)

    scope other.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 2)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()
    other = env.scopes['other']

    top_func_i32 = env.scopes['@top.func_i32']
    other_func_i32 = env.scopes['other.func_i32']
    top_func_i32_sym = top.find_sym('func_i32')
    other_func_i32_sym = other.find_sym('func_i32')
    assert top_func_i32_sym
    assert top_func_i32_sym.scope is top
    assert top_func_i32_sym.typ.is_function()
    assert top_func_i32_sym.typ.scope is top_func_i32
    assert top_func_i32.is_specialized()

    assert top_func_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert top_func_i32.return_type == Type.int(width=32)

    assert other_func_i32_sym
    assert other_func_i32_sym.scope is other
    assert other_func_i32_sym.typ.is_function()
    assert other_func_i32_sym.typ.scope is other_func_i32
    assert other_func_i32.is_specialized()

    assert other_func_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert other_func_i32.return_type == Type.int(width=32)
