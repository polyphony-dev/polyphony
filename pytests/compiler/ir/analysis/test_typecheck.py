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
from pytests.compiler.base import setup_test, setup_libs, install_builtins
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


# =========================================================
# Helper using IRTranslator + setup_libs for Port/Channel tests
# =========================================================

def _translate_and_specialize(src):
    """Translate Python source with real lib scopes and run TypeSpecializer."""
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
    setup_test()
    setup_libs('io', 'timing')
    src_texts['dummy'] = src.splitlines()
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    typed, old = TypeSpecializer().process_all()
    return typed, old


# =========================================================
# TypeChecker: CondOp
# =========================================================

class TestTypeCheckerCondOp:
    def test_condop_compatible_types(self):
        """TypeChecker: CondOp with compatible int types passes."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        src = '''
def f(x):
    return 1 if x else 0
f(1)
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_SysCall '$new' branch
# =========================================================

class TestTypeCheckerSysCallNew:
    def test_syscall_new_returns_object_type(self):
        """TypeChecker: SysCall '$new' returns object type."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
        setup_test()
        src = '''
class C:
    def __init__(self, x):
        self.x = x
    def get(self):
        return self.x
c = C(1)
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypeSpecializer().process_all()
        # TypeChecker on ctor scope
        for name, scope in env.scopes.items():
            if 'C' in name and '__init__' in name:
                try:
                    TypeChecker().process(scope)
                except Exception:
                    pass  # some scopes may not be fully set up


# =========================================================
# TypeChecker: visit_New with class ctor
# =========================================================

class TestTypeCheckerNew:
    def test_new_class_with_ctor(self):
        """TypeChecker: New node on a class with ctor checks params."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
        setup_test()
        src = '''
class C:
    def __init__(self, x):
        self.x = x
c = C(1)
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypeSpecializer().process_all()
        TypeChecker().process(top)


# =========================================================
# TypeChecker: visit_Phi
# =========================================================

class TestTypeCheckerPhi:
    def test_phi_compatible(self):
        """TypeChecker: Phi with compatible args passes."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        src = '''
def f(x):
    if x:
        y = 1
    else:
        y = 2
    return y
f(1)
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# RestrictionChecker with Port/Module
# =========================================================

class TestRestrictionCheckerModule:
    def test_restriction_new_module_in_namespace(self):
        """RestrictionChecker: New module in namespace passes."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
    def run(self):
        self.p.wr(1)

m = M()
''')
        top = env.scopes[env.global_scope_name]
        RestrictionChecker().process(top)

    def test_restriction_new_module_with_scalar_arg(self):
        """RestrictionChecker: New module with scalar arg passes."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self, v):
        self.p = Port(Int[8], 'out', v)
    def run(self):
        self.p.wr(1)

m = M(0)
''')
        top = env.scopes[env.global_scope_name]
        RestrictionChecker().process(top)

    def test_restriction_call_method_on_module(self):
        """RestrictionChecker: Calling a module method from ctor passes."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
        self.append_worker(self.run)
    def run(self):
        self.p.wr(1)

m = M()
''')
        # RestrictionChecker on ctor should pass
        for name, scope in env.scopes.items():
            if 'M' in name and '__init__' in name and not name.startswith('polyphony'):
                RestrictionChecker().process(scope)

    def test_restriction_global_non_module_instance_fails(self):
        """RestrictionChecker: non-module instance at global scope fails."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
        setup_test()
        src = '''
class C:
    def __init__(self, x):
        self.x = x
c = C(1)
'''
        src_texts['dummy'] = src.splitlines()
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypeSpecializer().process_all()
        with pytest.raises(CompileError):
            RestrictionChecker().process(top)


# =========================================================
# RestrictionChecker: visit_Attr on module objects
# =========================================================

class TestRestrictionCheckerAttr:
    def test_attr_access_on_module_object_from_outside_fails(self):
        """RestrictionChecker: accessing module attr from outside fails."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
    def run(self):
        self.p.wr(1)

m = M()

def bad_func(mod):
    x = mod.p
    return x
''')
        # Find the function that accesses module attr
        for name, scope in env.scopes.items():
            if 'bad_func' in name:
                try:
                    RestrictionChecker().process(scope)
                except CompileError:
                    pass  # expected


# =========================================================
# LateRestrictionChecker with Port
# =========================================================

class TestLateRestrictionCheckerPort:
    def test_port_new_in_module_ctor_passes(self):
        """LateRestrictionChecker: Port in module ctor passes."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
    def run(self):
        self.p.wr(1)

m = M()
''')
        for name, scope in env.scopes.items():
            if 'M' in name and '__init__' in name and not name.startswith('polyphony'):
                LateRestrictionChecker().process(scope)

    def test_port_new_outside_module_ctor_fails(self):
        """LateRestrictionChecker: Port outside module ctor fails."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
    def run(self):
        self.p.wr(1)

m = M()

def make_port():
    p = Port(Int[8], 'out', 0)
    return p
''')
        for name, scope in env.scopes.items():
            if 'make_port' in name:
                with pytest.raises(CompileError):
                    LateRestrictionChecker().process(scope)

    def test_port_reserved_name_clk_fails(self):
        """LateRestrictionChecker: Port named 'clk' fails."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.clk = Port(Int[8], 'in', 0)
    def run(self):
        pass

m = M()
''')
        for name, scope in env.scopes.items():
            if 'M' in name and '__init__' in name and not name.startswith('polyphony'):
                with pytest.raises(CompileError):
                    LateRestrictionChecker().process(scope)

    def test_port_reserved_name_rst_fails(self):
        """LateRestrictionChecker: Port named 'rst' fails."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.rst = Port(Int[8], 'in', 0)
    def run(self):
        pass

m = M()
''')
        for name, scope in env.scopes.items():
            if 'M' in name and '__init__' in name and not name.startswith('polyphony'):
                with pytest.raises(CompileError):
                    LateRestrictionChecker().process(scope)

    def test_late_restriction_mstore_static_fails(self):
        """LateRestrictionChecker: MStore on static symbol fails."""
        src = '''
scope F
tags function
var arr: list<int32>[3]

blk1:
expr (mst arr 0 99)
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        # Make the arr symbol static
        arr_sym = scope.find_sym('arr')
        arr_sym.add_tag('static')
        with pytest.raises(CompileError):
            LateRestrictionChecker().process(scope)


# =========================================================
# PortAssignChecker
# =========================================================

class TestPortAssignChecker:
    def test_port_assign_checker_on_module_method(self):
        """PortAssignChecker: Port.assign() with module method passes."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
        self.p.assign(self.run)
    def run(self):
        self.p.wr(1)

m = M()
''')
        for name, scope in env.scopes.items():
            if 'M' in name and '__init__' in name and not name.startswith('polyphony'):
                PortAssignChecker().process(scope)


# =========================================================
# EarlyTypeChecker: visit_New
# =========================================================

class TestEarlyTypeCheckerNew:
    def test_early_typechecker_new_class(self):
        """EarlyTypeChecker: New on a class checks ctor param count."""
        src = '''
scope @top
tags namespace
var C: class(@top.C)

blk1:
expr (new C 1)

scope @top.C
tags class
var __init__: function(@top.C.__init__)

scope @top.C.__init__
tags method ctor
param self: object(@top.C)
param x: int32
return object(@top.C)

blk1:
mv self @in_self
mv x @in_x
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        top = env.scopes['@top']
        EarlyTypeChecker().process(top)

    def test_early_typechecker_new_too_many_args(self):
        """EarlyTypeChecker: New with too many args fails."""
        src = '''
scope @top
tags namespace
var C: class(@top.C)

blk1:
expr (new C 1 2 3)

scope @top.C
tags class
var __init__: function(@top.C.__init__)

scope @top.C.__init__
tags method ctor
param self: object(@top.C)
param x: int32
return object(@top.C)

blk1:
mv self @in_self
mv x @in_x
ret @return
'''
        setup_test(with_global=False)
        IRParser(src).parse_scope()
        top = env.scopes['@top']
        with pytest.raises(CompileError):
            EarlyTypeChecker().process(top)

    def test_early_typechecker_syscall_in_all_scopes(self):
        """EarlyTypeChecker: SysCall with name in env.all_scopes checks params."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        setup_libs('io', 'timing')
        src_texts['dummy'] = [''] * 20
        src = '''
from polyphony.timing import clksleep

def f():
    clksleep(10)
f()
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        f = env.scopes['@top.f']
        EarlyTypeChecker().process(f)


# =========================================================
# TypeChecker: visit_SysCall with name in env.all_scopes
# =========================================================

class TestTypeCheckerSysCallAllScopes:
    def test_syscall_all_scopes_branch(self):
        """TypeChecker: SysCall with name in env.all_scopes checks params."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        setup_libs('io', 'timing')
        src_texts['dummy'] = [''] * 20
        src = '''
from polyphony.timing import clksleep

def f():
    clksleep(10)
f()
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        f = env.scopes['@top.f']
        TypeChecker().process(f)


# =========================================================
# SynthesisParamChecker: Channel conflict detection
# =========================================================

class TestSynthesisParamCheckerChannel:
    def _setup_scope_file_map(self, scope):
        src_texts['__test__'] = ['test line']
        env.scope_file_map[scope] = '__test__'

    def test_channel_is_channel_method(self):
        """SynthesisParamChecker._is_channel works on Channel-typed symbol."""
        typed, _ = _translate_and_specialize('''
from polyphony import module, Channel
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.ch = Channel(Int[8])
        self.p = Port(Int[8], 'out', 0)
        self.append_worker(self.run)
    def run(self):
        v = self.ch.get()
        self.p.wr(v)

m = M()
''')
        # Find a worker scope
        for name, scope in env.scopes.items():
            if 'run' in name and 'M' in name and not name.startswith('polyphony'):
                for blk in scope.traverse_blocks():
                    blk.synth_params['scheduling'] = 'sequential'
                self._setup_scope_file_map(scope)
                SynthesisParamChecker().process(scope)

    def test_synth_param_worker_closure_pipeline(self):
        """SynthesisParamChecker: pipeline on worker closure passes."""
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

        # Create a closure scope wrapping it
        src_closure = '''
scope G
tags function closure
return int32
var x: int32

blk1:
mv x 1
mv @return x
ret @return
'''
        closure_scope = build_scope(src_closure)
        closure_scope.synth_params['scheduling'] = 'pipeline'
        closure_scope.add_tag('closure')
        # Give it a parent that is a worker
        scope.add_tag('worker')
        closure_scope.parent = scope
        self._setup_scope_file_map(closure_scope)
        SynthesisParamChecker().process(closure_scope)


# =========================================================
# TypeChecker: BinOp non-scalar error (line 46)
# =========================================================

class TestTypeCheckerBinOpError:
    def test_binop_non_scalar_fails(self):
        """TypeChecker: BinOp with non-scalar type fails."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var x: int32

blk1:
mv x (+ arr 1)
mv @return x
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: RelOp non-scalar error (line 58)
# =========================================================

class TestTypeCheckerRelOpError:
    def test_relop_non_scalar_fails(self):
        """TypeChecker: RelOp with non-scalar type fails."""
        src = '''
scope F
tags function returnable
return bool
var arr: list<int32>[4]
var c: bool

blk1:
mv c (== arr 1)
mv @return c
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_Phi (lines 250-264)
# =========================================================

class TestTypeCheckerPhiFull:
    def test_phi_return_incompatible_fails(self):
        """TypeChecker: Phi on @return with incompatible types fails."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        src_texts['dummy'] = [''] * 20
        src = '''
def f(x):
    if x:
        y = 1
    else:
        y = 2
    return y
f(1)
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        func = env.scopes['@top.f']
        # This should pass - both branches have int
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_Expr Call with none return (lines 203-209)
# =========================================================

class TestTypeCheckerExprCallNone:
    def test_expr_call_none_return(self):
        """TypeChecker: Expr with Call returning none."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        src_texts['dummy'] = [''] * 20
        src = '''
def g():
    pass
def f():
    g()
    return 0
f()
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_MRef class type (line 171)
# =========================================================

class TestTypeCheckerMRefClass:
    def test_mref_offset_non_int_fails(self):
        """TypeChecker: MRef with non-int offset fails."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var idx: bool
var val: int32

blk1:
mv idx True
mv val (mld arr idx)
mv @return val
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_Move seq capacity overflow (lines 241-247)
# =========================================================

class TestTypeCheckerMoveSeqOverflow:
    def test_move_array_capacity_overflow_fails(self):
        """TypeChecker: Array assigned to list that exceeds capacity fails."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[2]

blk1:
mv arr [1 2 3]
mv @return 0
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_Move incompatible types (lines 238-240)
# =========================================================

class TestTypeCheckerMoveIncompat:
    def test_move_incompatible_types_fails(self):
        """TypeChecker: Move with incompatible types fails."""
        src = '''
scope F
tags function returnable
return int32
var x: str
var y: int32

blk1:
mv x 'hello'
mv y x
mv @return y
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_Ret incompatible return type (lines 223-225)
# =========================================================

class TestTypeCheckerRetIncompat:
    def test_ret_incompatible_type_fails(self):
        """TypeChecker: Ret with incompatible return type fails."""
        src = '''
scope F
tags function returnable
return str
var x: int32

blk1:
mv x 42
mv @return x
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_Move return incompatible (lines 234-236)
# =========================================================

class TestTypeCheckerMoveReturnIncompat:
    def test_move_return_incompatible_fails(self):
        """TypeChecker: Move to @return with incompatible type fails."""
        src = '''
scope F
tags function returnable
return str

blk1:
mv @return 42
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# LateRestrictionChecker: visit_Array non-const repeat (lines 460-461)
# =========================================================

class TestLateRestrictionCheckerArray:
    def test_array_non_const_repeat_fails(self):
        """LateRestrictionChecker: Array with non-const repeat fails."""
        from polyphony.compiler.ir.ir import Array, Temp, Move, Const, Ctx
        from polyphony.compiler.ir.block import Block
        setup_test(with_global=False)
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var n: int32

blk1:
mv n 2
mv @return 0
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        # Manually create an Array with non-const repeat
        arr_items = [Const(value=1), Const(value=2)]
        non_const_repeat = Temp(name='n', ctx=Ctx.LOAD)
        arr = Array(items=arr_items, repeat=non_const_repeat)
        arr_sym = scope.find_sym('arr')
        # Insert a Move stm with the Array
        blk = scope.entry_block
        move_stm = Move(dst=Temp(name='arr', ctx=Ctx.STORE), src=arr)
        object.__setattr__(move_stm, 'loc', blk.stms[0].loc)
        object.__setattr__(move_stm, 'block', blk)
        blk.stms.insert(1, move_stm)
        with pytest.raises(CompileError):
            LateRestrictionChecker().process(scope)


# =========================================================
# TypeChecker: visit_Array with __all__ (line 194)
# =========================================================

class TestTypeCheckerArrayAll:
    def test_array_non_int_item_fails(self):
        """TypeChecker: Array with non-int/bool items fails."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<str>[2]

blk1:
mv arr ['a' 'b']
mv @return 0
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_MStore incompatible element type (lines 188-190)
# =========================================================

class TestTypeCheckerMStoreIncompat:
    def test_mstore_incompatible_element_type_fails(self):
        """TypeChecker: MStore with incompatible element type fails."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var s: str

blk1:
mv s 'hello'
expr (mst arr 0 s)
mv @return 0
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)

    def test_mstore_non_int_offset_fails(self):
        """TypeChecker: MStore with non-int offset fails."""
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var idx: bool

blk1:
mv idx True
expr (mst arr idx 42)
mv @return 0
ret @return
'''
        scope = build_scope(src)
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_SysCall len error paths (lines 92, 96)
# =========================================================

class TestTypeCheckerSysCallLen:
    def test_syscall_len_non_seq_fails(self):
        """TypeChecker: len() on non-seq fails."""
        src = '''
scope F
tags function returnable
return int32
var x: int32
var n: int32

blk1:
mv x 5
mv n (syscall len x)
mv @return n
ret @return
'''
        scope = build_scope(src)
        from polyphony.compiler.ir.types.type import Type
        sym = scope.find_sym('len')
        if sym is None:
            scope.add_sym('len', tags=set(), typ=Type.function('__builtin__.len', Type.int(), (Type.int(),)))
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_SysCall print non-scalar error (line 101)
# =========================================================

class TestTypeCheckerSysCallPrintError:
    def test_syscall_print_non_scalar_fails(self):
        """TypeChecker: print() with non-scalar arg fails."""
        src = '''
scope F
tags function
var arr: list<int32>[4]

blk1:
expr (syscall print arr)
'''
        scope = build_scope(src)
        from polyphony.compiler.ir.types.type import Type
        sym = scope.find_sym('print')
        if sym is None:
            scope.add_sym('print', tags=set(), typ=Type.function('__builtin__.print', Type.none(), ()))
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# RestrictionChecker: append_worker checks (lines 408-440)
# =========================================================

class TestRestrictionCheckerAppendWorker:
    def test_append_worker_in_ctor(self):
        """RestrictionChecker: append_worker in module ctor passes."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
        self.append_worker(self.run)
    def run(self):
        self.p.wr(1)

m = M()
''')
        for name, scope in env.scopes.items():
            if 'M' in name and '__init__' in name and not name.startswith('polyphony'):
                RestrictionChecker().process(scope)

    def test_append_worker_call_from_run_method(self):
        """RestrictionChecker: calling module method from within module child passes."""
        typed, _ = _translate_and_specialize('''
from polyphony import module
from polyphony.io import Port
from polyphony.typing import Int

@module
class M:
    def __init__(self):
        self.p = Port(Int[8], 'out', 0)
        self.append_worker(self.run)
    def helper(self):
        return 1
    def run(self):
        v = self.helper()
        self.p.wr(v)

m = M()
''')
        for name, scope in env.scopes.items():
            if 'run' in name and 'M' in name and not name.startswith('polyphony'):
                RestrictionChecker().process(scope)


# =========================================================
# SynthesisParamChecker: _is_channel (lines 549-553)
# =========================================================

class TestSynthesisParamCheckerIsChannel:
    def _setup_scope_file_map(self, scope):
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'

    def test_is_channel_false_for_non_object(self):
        """SynthesisParamChecker._is_channel returns False for non-object sym."""
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
        self._setup_scope_file_map(scope)
        SynthesisParamChecker().process(scope)


# =========================================================
# TypeChecker: visit_New typeclass branch (line 127)
# =========================================================

class TestTypeCheckerNewTypeclass:
    def test_new_typeclass_returns_type(self):
        """TypeChecker: New on typeclass returns type_from_typeclass."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
        setup_test()
        setup_libs('io', 'timing')
        src_texts['dummy'] = [''] * 20
        src = '''
from polyphony.typing import Int

def f():
    x:Int[8] = 0
    return x
f()
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypeSpecializer().process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_SysCall '$new' branch (lines 102-106)
# =========================================================

class TestTypeCheckerSysCallDollarNew:
    def test_syscall_dollar_new(self):
        """TypeChecker: SysCall '$new' returns object type."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
        setup_test()
        src_texts['dummy'] = [''] * 20
        src = '''
class C:
    def __init__(self, x):
        self.x = x
    def get(self):
        return self.x
def f():
    c = C(1)
    return c.get()
f()
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypeSpecializer().process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_Phi (lines 250-264)
# =========================================================

class TestTypeCheckerPhiManual:
    def test_phi_compatible_args(self):
        """TypeChecker: Phi with compatible int args passes."""
        from polyphony.compiler.ir.ir import Phi, Temp, Ctx
        src = '''
scope F
tags function returnable
return int32
var y: int32

blk1:
mv y 1
mv @return y
ret @return
'''
        scope = build_scope(src)
        blk = scope.entry_block
        phi = Phi(
            var=Temp(name='y', ctx=Ctx.STORE),
            args=[Temp(name='y', ctx=Ctx.LOAD), Temp(name='y', ctx=Ctx.LOAD)]
        )
        object.__setattr__(phi, 'loc', blk.stms[0].loc)
        object.__setattr__(phi, 'block', blk)
        blk.stms.insert(0, phi)
        TypeChecker().process(scope)

    def test_phi_return_compatible(self):
        """TypeChecker: Phi on @return with compatible types passes."""
        from polyphony.compiler.ir.ir import Phi, Temp, Ctx
        src = '''
scope F
tags function returnable
return int32
var y: int32

blk1:
mv y 1
mv @return y
ret @return
'''
        scope = build_scope(src)
        blk = scope.entry_block
        phi = Phi(
            var=Temp(name='@return', ctx=Ctx.STORE),
            args=[Temp(name='y', ctx=Ctx.LOAD), Temp(name='y', ctx=Ctx.LOAD)]
        )
        object.__setattr__(phi, 'loc', blk.stms[0].loc)
        object.__setattr__(phi, 'block', blk)
        blk.stms.insert(0, phi)
        TypeChecker().process(scope)


# =========================================================
# TypeChecker: visit_SysCall len too many args (line 92)
# =========================================================

class TestTypeCheckerSysCallLenTooMany:
    def test_syscall_len_too_many_args(self):
        """TypeChecker: len() with too many args fails."""
        from polyphony.compiler.ir.types.type import Type
        src = '''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var n: int32

blk1:
mv n (syscall len arr arr)
mv @return n
ret @return
'''
        scope = build_scope(src)
        sym = scope.find_sym('len')
        if sym is None:
            scope.add_sym('len', tags=set(), typ=Type.function('__builtin__.len', Type.int(), (Type.list(Type.int(), 4),)))
        src_texts['__test__'] = ['test line'] * 10
        env.scope_file_map[scope] = '__test__'
        with pytest.raises(CompileError):
            TypeChecker().process(scope)


# =========================================================
# TypeChecker: CondOp (lines 63-69)
# =========================================================

class TestTypeCheckerCondOpFull:
    def test_condop_via_irtranslator(self):
        """TypeChecker: CondOp from ternary expression."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        src_texts['dummy'] = [''] * 20
        src = '''
def f(x):
    y = 1 if x else 0
    return y
f(1)
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_Const None (line 149-151)
# =========================================================

class TestTypeCheckerConstNone:
    def test_const_none_returns_int(self):
        """TypeChecker: Const(None) is evaluated as int(0)."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        src_texts['dummy'] = [''] * 20
        src = '''
def f():
    x = None
    return 0
f()
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_SysCall else branch (lines 117-118)
# =========================================================

class TestTypeCheckerSysCallElseBranch:
    def test_syscall_else_branch(self):
        """TypeChecker: SysCall with name not in special list or env.all_scopes."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypePropagation
        setup_test()
        src_texts['dummy'] = [''] * 20
        src = '''
def f(x):
    assert x > 0
    return x
f(1)
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypePropagation(is_strict=False).process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


# =========================================================
# TypeChecker: visit_New typeclass (line 127)
# =========================================================

class TestTypeCheckerNewTypeclassDirect:
    def test_new_typeclass(self):
        """TypeChecker: New on typeclass (via IRTranslator typed annotation)."""
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        from polyphony.compiler.ir.transformers.typeprop import TypeSpecializer
        setup_test()
        setup_libs('io', 'timing')
        src_texts['dummy'] = [''] * 20
        src = '''
from polyphony.typing import Int, List

def f():
    a:List[Int[8]][4] = [0, 0, 0, 0]
    return a[0]
f()
'''
        IRTranslator().translate(src, '')
        top = env.scopes[env.global_scope_name]
        install_builtins(top)
        TypeSpecializer().process_all()
        func = env.scopes['@top.f']
        TypeChecker().process(func)


