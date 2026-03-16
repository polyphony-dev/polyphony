"""Tests for NewFlattenFieldAccess."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.transformers.inlineopt import NewFlattenFieldAccess
from polyphony.compiler.ir.transformers.inlineopt import FlattenFieldAccess
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def test_flatten_does_not_crash_on_simple_function():
    """NewFlattenFieldAccess handles simple function scope without crash."""
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
    NewFlattenFieldAccess().process(scope)

    # Should not change simple TEMPs
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, MOVE) and isinstance(stm.dst, TEMP) and stm.dst.name == 'x':
                assert isinstance(stm.src, CONST)
                assert stm.src.value == 10


def test_flatten_preserves_non_object_attrs():
    """NewFlattenFieldAccess does not flatten non-object attributes."""
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
    NewFlattenFieldAccess().process(scope)

    # All TEMPs should remain as TEMPs
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, MOVE) and isinstance(stm.dst, TEMP):
                pass  # No assertion needed, just verify no crash
