"""Tests for AliasVarDetector."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IrReader as IrParser
from polyphony.compiler.ir.analysis.regreducer import AliasVarDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src, scheduling='sequential'):
    setup_test()
    parser = IrParser(src)
    parser.parse_scope()
    name = list(parser.sources)[0]
    scope = env.scopes[name]
    # Set scheduling on all blocks since IrReader doesn't support it
    for blk in scope.traverse_blocks():
        blk.synth_params['scheduling'] = scheduling
    return scope


def test_alias_condition_var():
    """AliasVarDetector tags condition variables as alias."""
    src = '''
scope F
tags function returnable
return int32
var cond: bool condition
var x: int32

blk1:
mv cond 1
mv x 10
mv @return x
ret @return
'''
    scope = build_scope(src)
    AliasVarDetector().process(scope)

    sym = scope.find_sym('cond')
    assert sym.is_alias(), f'Expected cond to be alias but it is not'


def test_alias_simple_move():
    """AliasVarDetector tags single-def variables as alias."""
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
    AliasVarDetector().process(scope)

    sym = scope.find_sym('x')
    assert sym.is_alias(), f'Expected x to be alias but it is not'


def test_alias_not_tagged_for_return():
    """AliasVarDetector does not tag return variables as alias."""
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
    AliasVarDetector().process(scope)

    ret_sym = scope.find_sym('@return')
    assert not ret_sym.is_alias(), f'Expected @return to NOT be alias'


def test_alias_multiple_vars():
    """AliasVarDetector tags multiple single-def variables as alias."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: bool condition

blk1:
mv a 5
mv b a
mv c 1
mv @return b
ret @return
'''
    scope = build_scope(src)
    AliasVarDetector().process(scope)
    aliases = {sym.name for sym in scope.symbols.values() if sym.is_alias()}
    assert 'a' in aliases
    assert 'b' in aliases
    assert 'c' in aliases
    assert '@return' not in aliases
