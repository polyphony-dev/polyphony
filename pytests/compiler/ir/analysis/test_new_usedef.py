"""Tests for UseDefDetector (new IR version)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.usedef import UseDefDetector
from polyphony.compiler.ir.analysis.usedef import UseDefDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def has_const_value(consts, value):
    return any(c.value == value for c in consts)


def test_simple_move():
    """mv x 1: x is defined, 1 is a const use."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)

    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    blk = scope.entry_block
    stm = blk.stms[0]

    assert stm in usedef.get_stms_defining(x_sym)
    assert stm not in usedef.get_stms_using(x_sym)
    assert has_const_value(usedef.get_consts_used_at(stm), 1)


def test_move_var_to_var():
    """mv y x: x is used, y is defined."""
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 1
mv y x
'''
    scope = build_scope(src)

    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    stm1 = scope.entry_block.stms[1]

    assert stm1 in usedef.get_stms_defining(y_sym)
    assert stm1 in usedef.get_stms_using(x_sym)


def test_binop_uses():
    """mv z (+ x y): x, y used; z defined."""
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y 2
mv z (+ x y)
'''
    scope = build_scope(src)

    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    z_sym = scope.find_sym('z')
    stm2 = scope.entry_block.stms[2]

    assert stm2 in usedef.get_stms_defining(z_sym)
    assert stm2 in usedef.get_stms_using(x_sym)
    assert stm2 in usedef.get_stms_using(y_sym)


def test_call_uses():
    """mv r (call f a): f, a used; r defined."""
    src = '''
scope F
tags function
var f: function(F)
var a: int32
var r: int32

blk1:
mv a 1
mv r (call f a)
'''
    scope = build_scope(src)

    usedef = UseDefDetector().process(scope)

    f_sym = scope.find_sym('f')
    a_sym = scope.find_sym('a')
    r_sym = scope.find_sym('r')
    stm1 = scope.entry_block.stms[1]

    assert stm1 in usedef.get_stms_defining(r_sym)
    assert stm1 in usedef.get_stms_using(f_sym)
    assert stm1 in usedef.get_stms_using(a_sym)


def test_get_all_def_use_syms():
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y x
mv z (+ x y)
'''
    scope = build_scope(src)

    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    z_sym = scope.find_sym('z')

    all_def = usedef.get_all_def_syms()
    assert x_sym in all_def
    assert y_sym in all_def
    assert z_sym in all_def

    all_use = usedef.get_all_use_syms()
    assert x_sym in all_use
    assert y_sym in all_use
    assert z_sym not in all_use


def test_attr_def_use():
    """mv self.x v: self used, self.x defined, v used."""
    src = '''
scope C
tags class
var x: int32

scope C.__init__
tags method ctor
param self:object(C)
param x:int32
return object(C)

blk1:
mv x @in_x
mv self.x x
'''
    scope = build_scope(src)
    ctor = env.scopes['C.__init__']

    usedef = UseDefDetector().process(ctor)

    self_sym = ctor.find_sym('self')
    x_sym = ctor.find_sym('x')
    stm1 = ctor.entry_block.stms[1]

    assert stm1 in usedef.get_stms_using(x_sym)
    assert stm1 in usedef.get_stms_using(self_sym)


def test_matches_old_usedef():
    """UseDefDetector should produce equivalent results to old UseDefDetector."""
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y 2
mv z (+ x y)
'''
    scope = build_scope(src)

    # Old detector on old IR
    old_usedef = UseDefDetector().process(scope)

    # New detector on new IR
    new_usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    z_sym = scope.find_sym('z')

    # Same def/use symbols
    assert set(old_usedef.get_all_def_syms()) == set(new_usedef.get_all_def_syms())
    assert set(old_usedef.get_all_use_syms()) == set(new_usedef.get_all_use_syms())

    # Same number of definitions per symbol
    for sym in [x_sym, y_sym, z_sym]:
        assert len(old_usedef.get_stms_defining(sym)) == len(new_usedef.get_stms_defining(sym))
        assert len(old_usedef.get_stms_using(sym)) == len(new_usedef.get_stms_using(sym))


def test_usedef_table_accepts_new_ir_stm():
    """UseDefTable query methods must accept new IR stm types.
    This was a bug: isinstance checks only matched old IrStm."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)

    usedef = UseDefDetector().process(scope)

    stm = scope.entry_block.stms[0]
    # These must not raise AssertionError
    vars_def = usedef.get_vars_defined_at(stm)
    assert len(vars_def) == 1
    syms_def = usedef.get_syms_defined_at(stm)
    assert len(syms_def) == 1
    vars_used = usedef.get_vars_used_at(stm)
    consts = usedef.get_consts_used_at(stm)
