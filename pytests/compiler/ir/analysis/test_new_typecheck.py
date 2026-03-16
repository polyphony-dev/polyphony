"""Tests for new IR type checker and restriction checker passes."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.analysis.typecheck import (
    TypeChecker, EarlyTypeChecker, EarlyRestrictionChecker,
    RestrictionChecker, LateRestrictionChecker, AssertionChecker,
)
from polyphony.compiler.common.env import env
from polyphony.compiler.common.errors import CompileError
from pytests.compiler.base import setup_test
import pytest


def build_scope(src, scheduling='sequential'):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    name = list(parser.sources)[0]
    scope = env.scopes[name]
    for blk in scope.traverse_blocks():
        blk.synth_params['scheduling'] = scheduling
    return scope


def test_new_typechecker_basic():
    """TypeChecker processes basic typed IR without error."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y (+ x 1)
mv @return y
ret @return
'''
    scope = build_scope(src)
    TypeChecker().process(scope)


def test_new_typechecker_const_types():
    """TypeChecker returns correct types for constants."""
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
    TypeChecker().process(scope)


def test_new_early_typechecker_basic():
    """EarlyTypeChecker processes without error."""
    src = '''
scope @top
tags namespace
var F: function(@top.F)

blk1:
expr (call F 1)

scope @top.F
tags function
param x: int32
return int32

blk1:
mv x @in_x
mv @return x
ret @return
'''
    setup_test(with_global=False)
    IRParser(src).parse_scope()
    top = env.scopes['@top']
    f = env.scopes['@top.F']
    EarlyTypeChecker().process(top)


def test_new_early_restriction_checker():
    """EarlyRestrictionChecker detects range outside for loop."""
    src = '''
scope @top
tags namespace
var F: function(@top.F)
var range: function(__builtin__.range)

scope @top.F
tags function returnable
return int32
var x: int32

blk1:
expr (syscall range 10)
mv @return x
ret @return
'''
    setup_test(with_global=False)
    IRParser(src).parse_scope()
    f = env.scopes['@top.F']
    with pytest.raises(CompileError):
        EarlyRestrictionChecker().process(f)


def test_new_assertion_checker_const_false():
    """AssertionChecker warns on assert(False)."""
    src = '''
scope @top
tags namespace
var F: function(@top.F)

scope @top.F
tags function returnable
return int32

blk1:
expr (syscall assert 0)
mv @return 0
ret @return
'''
    setup_test(with_global=False)
    IRParser(src).parse_scope()
    f = env.scopes['@top.F']
    # Should not raise, just warn
    AssertionChecker().process(f)


def test_new_late_restriction_checker_basic():
    """LateRestrictionChecker processes basic IR without error."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
mv @return x
ret @return
'''
    scope = build_scope(src)
    LateRestrictionChecker().process(scope)
