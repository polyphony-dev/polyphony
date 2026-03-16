"""Tests for NewTypePropagation, NewTypeSpecializer, and NewStaticTypePropagation."""
from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new_ir
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.transformers.typeprop import (
    NewTypePropagation, NewTypeSpecializer, NewStaticTypePropagation,
)
from polyphony.compiler.ir.transformers.typeprop import TypePropagation, TypeSpecializer
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.builtin import builtin_symbols
from pytests.compiler.base import setup_test, install_builtins
import pytest


def test_new_type_specializer_basic():
    """NewTypeSpecializer specializes a function called with int arg."""
    setup_test(with_global=False)
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

    NewTypeSpecializer().process_all()

    func_i32 = env.scopes['@top.func_i32']
    assert func_i32.is_specialized()
    assert func_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert func_i32.return_type == Type.int(width=32)


def test_new_type_specializer_two_modules():
    """NewTypeSpecializer specializes functions from two namespaces."""
    setup_test(with_global=False)
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

    NewTypeSpecializer().process_all()

    top_func_i32 = env.scopes['@top.func_i32']
    other_func_i32 = env.scopes['other.func_i32']
    assert top_func_i32.is_specialized()
    assert other_func_i32.is_specialized()
    assert top_func_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert other_func_i32.param_types() == (Type.int(width=32, explicit=True),)


def test_new_type_propagation_basic():
    """NewTypePropagation propagates basic int types."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func 1)

    scope @top.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = NewTypePropagation(is_strict=False).process_all()

    func = env.scopes['@top.func']
    assert func in typed_scopes
    x_sym = func.find_sym('x')
    assert x_sym.typ.is_int()


def test_new_static_type_propagation_basic():
    """NewStaticTypePropagation propagates types for static scopes."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef
    blk1:
        mv x 42
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    NewStaticTypePropagation(is_strict=False).process_scopes([top])

    x_sym = top.find_sym('x')
    assert x_sym.typ.is_int()
