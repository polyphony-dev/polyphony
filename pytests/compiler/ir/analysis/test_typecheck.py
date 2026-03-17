"""Tests for new IR type checker and restriction checker passes."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.analysis.typecheck import (
    TypeChecker, EarlyTypeChecker, EarlyRestrictionChecker,
    RestrictionChecker, LateRestrictionChecker, AssertionChecker,
    PortAssignChecker, SynthesisParamChecker,
)
from polyphony.compiler.common.env import env
from polyphony.compiler.common.common import src_texts
from polyphony.compiler.common.errors import CompileError
from pytests.compiler.base import setup_test, register_lib_syms
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


def build_scopes_noglobal(src, scheduling='sequential'):
    """Build scopes without global scope (for @top definitions)."""
    setup_test(with_global=False)
    parser = IRParser(src)
    parser.parse_scope()
    register_lib_syms()
    scopes = {}
    for name in parser.sources:
        scope = env.scopes[name]
        for blk in scope.traverse_blocks():
            blk.synth_params['scheduling'] = scheduling
        scopes[name] = scope
    return scopes


# =========================================================
# TypeChecker expression visitors
# =========================================================

class TestTypeCheckerConst:
    def test_const_bool_true(self):
        src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x True
mv @return x
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_const_bool_false(self):
        src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x False
mv @return x
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_const_string(self):
        src = '''
scope F
tags function returnable
return str
var x: str

blk1:
mv x 'hello'
mv @return x
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_const_int(self):
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


class TestTypeCheckerUnOp:
    def test_unop(self):
        src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x -5
mv @return x
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerBinOp:
    def test_binop_add(self):
        src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y 2
mv z (+ x y)
mv @return z
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_binop_bool_add(self):
        """bool + bool (non-bitwise) should return int(2)."""
        src = '''
scope F
tags function returnable
return int32
var a: bool
var b: bool
var c: int32

blk1:
mv a True
mv b False
mv c (+ a b)
mv @return c
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_binop_bool_bitwise(self):
        """Bitwise operation on bools stays bool."""
        src = '''
scope F
tags function returnable
return bool
var a: bool
var b: bool
var c: bool

blk1:
mv a True
mv b False
mv c (& a b)
mv @return c
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_binop_mult_list_int(self):
        """list * int returns list type."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var n: int32
var arr2: list<int32>[4]

blk1:
mv n 2
mv arr2 (* arr n)
mv @return 0
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerRelOp:
    def test_relop_int(self):
        src = '''
scope F
tags function returnable
return bool
var x: int32
var y: int32
var c: bool

blk1:
mv x 1
mv y 2
mv c (== x y)
mv @return c
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerMRef:
    def test_mref_list(self):
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var idx: int32
var val: int32

blk1:
mv idx 0
mv val (mld arr idx)
mv @return val
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerMStore:
    def test_mstore_list(self):
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var idx: int32

blk1:
mv idx 0
expr (mst arr idx 42)
mv @return idx
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerArray:
    def test_array_int_items(self):
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[3]

blk1:
mv arr [1 2 3]
mv @return 0
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerJumps:
    def test_cjump(self):
        src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv c True
mv x 0
cj c blk2 blk3

blk2:
mv x 1
j blk4

blk3:
mv x 2
j blk4

blk4:
mv @return x
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_jump(self):
        src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv @return x
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)

    def test_mcjump(self):
        src = '''
scope F
tags function returnable
return int32
var c1: bool
var c2: bool
var x: int32

blk1:
mv c1 True
mv c2 False
mv x 0
mj c1 blk2 c2 blk3

blk2:
mv x 1
j blk4

blk3:
mv x 2
j blk4

blk4:
mv @return x
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerRet:
    def test_ret_compatible(self):
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


class TestTypeCheckerMove:
    def test_move_basic(self):
        src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 1
mv y x
mv @return y
ret @return
'''
        scope = build_scope(src)
        TypeChecker().process(scope)


class TestTypeCheckerExpr:
    def test_expr_call(self):
        """Expr with a Call whose return type is none."""
        src = '''
scope NS
tags namespace
var G: function(NS.G)

blk1:
expr (call G 1)

scope NS.G
tags function
param x: int32
return none

blk1:
mv x @in_x
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        TypeChecker().process(ns)


class TestTypeCheckerAttr:
    def test_attr_access(self):
        """Test visit_Attr through attribute access on objects."""
        src = '''
scope C
tags class
var x: int32

scope C.__init__
tags method ctor function
param self: object(C)
param x: int32
return object(C)

blk1:
mv x @in_x
mv self.x x
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ctor = env.scopes['C.__init__']
        TypeChecker().process(ctor)


class TestTypeCheckerTemp:
    def test_temp_lookup(self):
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
        TypeChecker().process(scope)


class TestTypeCheckerCall:
    def test_call_basic(self):
        src = '''
scope NS
tags namespace
var G: function(NS.G)

blk1:
expr (call G 1)

scope NS.G
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
        ns = env.scopes['NS']
        TypeChecker().process(ns)

    def test_call_lib_function(self):
        """Call to a lib function returns its return type."""
        src = '''
scope NS
tags namespace
var G: function(NS.G)

blk1:
expr (call G 1)

scope NS.G
tags lib function
param x: int32
return int32
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        TypeChecker().process(ns)

class TestTypeCheckerSysCall:
    def test_syscall_len(self):
        """SysCall 'len' with a seq argument."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var n: int32

blk1:
mv n (syscall len arr)
mv @return n
ret @return
'''
        scope = build_scope(src)
        from polyphony.compiler.ir.types.type import Type
        sym = scope.find_sym('len')
        if sym is None:
            scope.add_sym('len', tags=set(), typ=Type.function('__builtin__.len', Type.int(), (Type.list(Type.int(), 4),)))
        TypeChecker().process(scope)

    def test_syscall_print(self):
        """SysCall 'print' with scalar args."""
        src = '''
scope F
tags function
var x: int32

blk1:
mv x 5
expr (syscall print x)
'''
        scope = build_scope(src)
        from polyphony.compiler.ir.types.type import Type
        sym = scope.find_sym('print')
        if sym is None:
            scope.add_sym('print', tags=set(), typ=Type.function('__builtin__.print', Type.none(), ()))
        TypeChecker().process(scope)

# =========================================================
# EarlyTypeChecker
# =========================================================

class TestEarlyTypeChecker:
    def test_early_typechecker_call_matching_params(self):
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1 2)

scope NS.F
tags function
param a: int32
param b: int32
return int32

blk1:
mv a @in_a
mv b @in_b
mv @return a
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        EarlyTypeChecker().process(ns)

    def test_early_typechecker_too_few_args(self):
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F)

scope NS.F
tags function
param a: int32
return int32

blk1:
mv a @in_a
mv @return a
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        with pytest.raises(CompileError):
            EarlyTypeChecker().process(ns)

    def test_early_typechecker_too_many_args(self):
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1 2 3)

scope NS.F
tags function
param a: int32
return int32

blk1:
mv a @in_a
mv @return a
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        with pytest.raises(CompileError):
            EarlyTypeChecker().process(ns)

    def test_early_typechecker_lib_call(self):
        """EarlyTypeChecker on lib function returns its return type."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1)

scope NS.F
tags lib function
param a: int32
return int32
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        EarlyTypeChecker().process(ns)

# =========================================================
# EarlyRestrictionChecker
# =========================================================

class TestEarlyRestrictionChecker:
    def test_range_outside_for(self):
        """range syscall outside for should fail."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)

scope NS.F
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
        f = env.scopes['NS.F']
        # Add range symbol
        from polyphony.compiler.ir.types.type import Type
        f.add_sym('range', tags=set(), typ=Type.function('__builtin__.range', Type.int(), ()))
        with pytest.raises(CompileError):
            EarlyRestrictionChecker().process(f)


# =========================================================
# AssertionChecker
# =========================================================

class TestAssertionChecker:
    def test_assert_true_no_warn(self):
        src = '''
scope NS
tags namespace
var F: function(NS.F)

scope NS.F
tags function returnable
return int32

blk1:
expr (syscall assert 1)
mv @return 0
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        f = env.scopes['NS.F']
        AssertionChecker().process(f)

    def test_assert_non_assert_syscall(self):
        src = '''
scope NS
tags namespace
var F: function(NS.F)
var print: function(__builtin__.print)

scope NS.F
tags function returnable
return int32

blk1:
expr (syscall print 1)
mv @return 0
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        f = env.scopes['NS.F']
        AssertionChecker().process(f)


# =========================================================
# LateRestrictionChecker
# =========================================================

class TestLateRestrictionChecker:
    def test_late_restriction_move_basic(self):
        src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y x
mv @return y
ret @return
'''
        scope = build_scope(src)
        LateRestrictionChecker().process(scope)


# =========================================================
# TypeChecker _check_param_number
# =========================================================

class TestCheckParamNumber:
    def test_call_too_few_args(self):
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F)

scope NS.F
tags function
param a: int32
return int32

blk1:
mv a @in_a
mv @return a
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        with pytest.raises(CompileError):
            TypeChecker().process(ns)

    def test_call_too_many_args(self):
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1 2 3)

scope NS.F
tags function
param a: int32
return int32

blk1:
mv a @in_a
mv @return a
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        ns = env.scopes['NS']
        with pytest.raises(CompileError):
            TypeChecker().process(ns)


# =========================================================
# SynthesisParamChecker
# =========================================================

class TestSynthesisParamChecker:
    def _setup_scope_file_map(self, scope):
        """Set up scope_file_map so SynthesisParamChecker can report errors."""
        src_texts['__test__'] = ['test line']
        env.scope_file_map[scope] = '__test__'

    def test_synth_param_basic(self):
        src = '''
scope F
tags function worker
return int32
var x: int32

blk1:
mv x 1
mv @return x
ret @return
'''
        scope = build_scope(src)
        scope.synth_params['scheduling'] = 'sequential'
        self._setup_scope_file_map(scope)
        SynthesisParamChecker().process(scope)

    def test_synth_param_pipeline_on_worker(self):
        src = '''
scope F
tags function worker
return int32
var x: int32

blk1:
mv x 1
mv @return x
ret @return
'''
        scope = build_scope(src)
        scope.synth_params['scheduling'] = 'pipeline'
        self._setup_scope_file_map(scope)
        SynthesisParamChecker().process(scope)

    def test_synth_param_pipeline_on_non_worker_fails(self):
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
        scope.synth_params['scheduling'] = 'pipeline'
        self._setup_scope_file_map(scope)
        with pytest.raises(CompileError):
            SynthesisParamChecker().process(scope)
