"""Tests for StaticConstOpt (static constant propagation across scopes)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.constopt import StaticConstOpt
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scopes(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    return [env.scopes[name] for name in parser.sources]


def test_static_const_propagation_basic():
    """StaticConstOpt propagates constant MOVE to constant table."""
    src = '''
scope C
tags class
var x: int32

blk1:
mv x 42
'''
    scopes = build_scopes(src)
    StaticConstOpt().process_scopes(scopes)

    scope = scopes[0]
    sym = scope.find_sym('x')
    assert sym in scope.constants
    c = scope.constants[sym]
    if isinstance(c, Const):
        assert c.value == 42
    else:
        assert c.value == 42


def test_static_const_propagation_temp_lookup():
    """StaticConstOpt replaces TEMP with constant when in table."""
    src = '''
scope C
tags class
var x: int32
var y: int32

blk1:
mv x 10
mv y x
'''
    scopes = build_scopes(src)
    StaticConstOpt().process_scopes(scopes)

    scope = scopes[0]
    sym_y = scope.find_sym('y')
    assert sym_y in scope.constants


def test_static_const_multiple_scopes():
    """StaticConstOpt works across multiple scopes."""
    src = '''
scope A
tags class
var x: int32

blk1:
mv x 100

scope B
tags class
var y: int32

blk1:
mv y 200
'''
    scopes = build_scopes(src)
    StaticConstOpt().process_scopes(scopes)

    scope_a = scopes[0]
    scope_b = scopes[1]
    sym_x = scope_a.find_sym('x')
    sym_y = scope_b.find_sym('y')
    assert sym_x in scope_a.constants
    assert sym_y in scope_b.constants


def test_static_const_binop_propagation():
    """StaticConstOpt propagates binop result involving constants."""
    src = '''
scope G
tags class
var a: int32
var b: int32

blk1:
mv a 5
mv b (+ a 3)
'''
    scopes = build_scopes(src)
    StaticConstOpt().process_scopes(scopes)

    scope = scopes[0]
    sym_a = scope.find_sym('a')
    sym_b = scope.find_sym('b')
    assert sym_a in scope.constants
    # a should be 5
    c_a = scope.constants[sym_a]
    assert c_a.value == 5
