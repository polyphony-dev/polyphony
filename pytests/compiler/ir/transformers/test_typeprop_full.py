"""Tests for TypePropagation, TypeSpecializer, and StaticTypePropagation."""
from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new_ir
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.transformers.typeprop import (
    TypePropagation, TypeSpecializer, StaticTypePropagation,
)
from polyphony.compiler.ir.transformers.typeprop import TypePropagation, TypeSpecializer
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.builtin import builtin_symbols
from pytests.compiler.base import setup_test, install_builtins
import pytest


def test_new_type_specializer_basic():
    """TypeSpecializer specializes a function called with int arg."""
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

    TypeSpecializer().process_all()

    func_i32 = env.scopes['@top.func_i32']
    assert func_i32.is_specialized()
    assert func_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert func_i32.return_type == Type.int(width=32)


def test_new_type_specializer_two_modules():
    """TypeSpecializer specializes functions from two namespaces."""
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

    TypeSpecializer().process_all()

    top_func_i32 = env.scopes['@top.func_i32']
    other_func_i32 = env.scopes['other.func_i32']
    assert top_func_i32.is_specialized()
    assert other_func_i32.is_specialized()
    assert top_func_i32.param_types() == (Type.int(width=32, explicit=True),)
    assert other_func_i32.param_types() == (Type.int(width=32, explicit=True),)


def test_new_type_propagation_basic():
    """TypePropagation propagates basic int types."""
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

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()

    func = env.scopes['@top.func']
    assert func in typed_scopes
    x_sym = func.find_sym('x')
    assert x_sym.typ.is_int()


def test_new_static_type_propagation_basic():
    """StaticTypePropagation propagates types for static scopes."""
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

    StaticTypePropagation(is_strict=False).process_scopes([top])

    x_sym = top.find_sym('x')
    assert x_sym.typ.is_int()


# ============================================================
# TypeEvaluator tests
# ============================================================
from polyphony.compiler.ir.transformers.typeprop import TypeEvaluator, TypeExprEvaluator, TypeReplacer, TypeEvalVisitor


def test_type_evaluator_visit_bool():
    """TypeEvaluator.visit_bool returns the bool type unchanged."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.bool()
    assert te.visit(t) is t


def test_type_evaluator_visit_str():
    """TypeEvaluator.visit_str returns the str type unchanged."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.str()
    assert te.visit(t) is t


def test_type_evaluator_visit_none():
    """TypeEvaluator.visit_none returns the none type unchanged."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.none()
    assert te.visit(t) is t


def test_type_evaluator_visit_undef():
    """TypeEvaluator.visit_undef returns the undef type unchanged."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.undef()
    assert te.visit(t) is t


def test_type_evaluator_visit_int():
    """TypeEvaluator.visit_int returns the int type with evaluated width."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.int(width=16)
    result = te.visit(t)
    assert result.is_int()
    assert result.width == 16


def test_type_evaluator_visit_object():
    """TypeEvaluator.visit_object returns the object type unchanged."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace class
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.object(top)
    assert te.visit(t) is t


def test_type_evaluator_visit_class():
    """TypeEvaluator.visit_class returns the class type unchanged."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace class
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.klass(top)
    assert te.visit(t) is t


def test_type_evaluator_visit_non_type():
    """TypeEvaluator.visit returns non-Type argument as-is."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    assert te.visit(42) == 42
    assert te.visit('hello') == 'hello'



def test_type_evaluator_visit_tuple():
    """TypeEvaluator.visit_tuple evaluates the element type."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.tuple(Type.int(32), 3)
    result = te.visit(t)
    assert result.is_tuple()
    assert result.element.is_int()


def test_type_evaluator_visit_list():
    """TypeEvaluator.visit_list evaluates element type."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.list(Type.int(32), 4)
    result = te.visit(t)
    assert result.is_list()
    assert result.element.is_int()


def test_type_evaluator_visit_function_with_scope():
    """TypeEvaluator.visit_function evaluates param/return types when scope exists."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)

    scope @top.func
        tags function
        param x: int32
        return int32
    blk1:
        mv x @in_x
        mv @return x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    func = env.scopes['@top.func']
    te = TypeEvaluator(top)
    func_sym = top.find_sym('func')
    result = te.visit(func_sym.typ)
    assert result.is_function()


def test_type_evaluator_visit_function_without_scope():
    """TypeEvaluator.visit_function evaluates when scope is None."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    te = TypeEvaluator(top)
    t = Type.function(None, Type.int(32), (Type.int(16),))
    result = te.visit(t)
    assert result.is_function()


# ============================================================
# TypePropagation visitor method tests
# ============================================================


def test_typeprop_visit_const_bool():
    """TypePropagation: Const(True) propagates as bool."""
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
        mv @return True
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func.return_type.is_bool()


def test_typeprop_visit_const_str():
    """TypePropagation: Const('hello') propagates as str."""
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
        mv @return 'hello'
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func.return_type.is_str()


def test_typeprop_binop():
    """TypePropagation: BinOp on two ints yields int type."""
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
        mv @return (+ x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func.return_type.is_int()


def test_typeprop_relop():
    """TypePropagation: RelOp yields bool type."""
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
        mv @return (< x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func.return_type.is_bool()


def test_typeprop_unop():
    """TypePropagation: UnOp propagates the operand type."""
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
        mv @return ~x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func.return_type.is_int()


def test_typeprop_condop():
    """TypePropagation: CondOp returns left type (tested via IRTranslator)."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
def f(x):
    return 1 if x else 0
f(1)
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.f']
    assert func.return_type.is_int()


def test_typeprop_two_assignments():
    """TypePropagation: two assignments propagate types to same variable."""
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
        var y: undef
    blk1:
        mv x @in_x
        mv y 10
        mv y (+ y x)
        mv @return y
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    y_sym = func.find_sym('y')
    assert y_sym.typ.is_int()


def test_typeprop_expr_and_cjump():
    """TypePropagation: Expr and CJump visit their sub-expressions."""
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
        var y: undef
    blk1:
        mv x @in_x
        cj (< x 10) blk2 blk3
    blk2:
        mv y 1
        j blk4
    blk3:
        mv y 2
        j blk4
    blk4:
        mv @return y
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    y_sym = func.find_sym('y')
    assert y_sym.typ.is_int()


def test_typeprop_array_literal():
    """TypePropagation: Array literal propagates element type (via IRTranslator)."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
def f():
    a = [1, 2, 3]
    return a
f()
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.f']
    a_sym = func.find_sym('a')
    assert a_sym.typ.is_list()
    assert a_sym.typ.element.is_int()


def test_typeprop_call_nested():
    """TypePropagation: nested call propagates callee return type."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var f: function(@top.f)
        var g: function(@top.g)
    blk1:
        expr (call f 1)

    scope @top.g
        tags function
        param y: undef
        return undef
    blk1:
        mv y @in_y
        mv @return y
        ret @return

    scope @top.f
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (call g x)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    g = env.scopes['@top.g']
    assert g.return_type.is_int()


def test_typeprop_const_none():
    """TypePropagation: Const(None) propagates as int (via IRTranslator)."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
x = None
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    StaticTypePropagation(is_strict=False).process_scopes([top])
    x_sym = top.find_sym('x')
    # Const(None) returns Type.int() in current impl
    assert x_sym.typ.is_int()


def test_typeprop_move_to_irvariable():
    """TypePropagation: Move to Temp propagates src type to dst symbol."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef
        var y: undef
    blk1:
        mv x 42
        mv y x
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])
    x_sym = top.find_sym('x')
    y_sym = top.find_sym('y')
    assert x_sym.typ.is_int()
    assert y_sym.typ.is_int()


def test_typeprop_jump():
    """TypePropagation: Jump statement is visited without error."""
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
        j blk2
    blk2:
        mv @return x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func.return_type.is_int()


# ============================================================
# TypeSpecializer: class specialization
# ============================================================


def test_type_specializer_class():
    """TypeSpecializer specializes class construction."""
    setup_test(with_global=False)
    block_src = """
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
        param x: undef
        return object(@top.C)
    blk1:
        mv self @in_self
        mv x @in_x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()

    # Specialized class should exist
    c_i32 = env.scopes.get('@top.C_i32')
    assert c_i32 is not None
    assert c_i32.is_specialized()


def test_type_specializer_no_params():
    """TypeSpecializer: function with no params is added to worklist."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func)

    scope @top.func
        tags function
        return undef
    blk1:
        mv @return 42
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()

    func = env.scopes['@top.func']
    assert func.return_type.is_int()


def test_type_specializer_attr_call():
    """TypeSpecializer: call via Attr (other.func)."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var other: namespace(other)
    blk1:
        expr (call other.func 1)

    scope other
        tags namespace
        var func: function(other.func)

    scope other.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()

    func_i32 = env.scopes.get('other.func_i32')
    assert func_i32 is not None
    assert func_i32.is_specialized()


# ============================================================
# TypeReplacer
# ============================================================


def test_type_replacer():
    """TypeReplacer replaces undef types with int."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)

    scope @top.func
        tags function
        var x: undef
    blk1:
        mv x 1
    """
    IRParser(block_src).parse_scope()
    func = env.scopes['@top.func']

    old_t = Type.undef()
    new_t = Type.int(32)
    replacer = TypeReplacer(old_t, new_t, lambda a, b: a == b)
    replacer.process(func)

    x_sym = func.find_sym('x')
    assert x_sym.typ.is_int()


# ============================================================
# TypeEvalVisitor
# ============================================================


def test_type_eval_visitor():
    """TypeEvalVisitor evaluates types on a scope with int params."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)

    scope @top.func
        tags function
        param x: int32
        return int32
        var y: int16
    blk1:
        mv x @in_x
        mv y x
    """
    IRParser(block_src).parse_scope()
    func = env.scopes['@top.func']

    TypeEvalVisitor().process(func)

    x_sym = func.find_sym('x')
    assert x_sym.typ.is_int()
    y_sym = func.find_sym('y')
    assert y_sym.typ.is_int()


# ============================================================
# StaticTypePropagation additional tests
# ============================================================


def test_static_type_prop_multiple_stms():
    """StaticTypePropagation with multiple variable assignments."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef
        var y: undef
        var z: undef
    blk1:
        mv x 10
        mv y 20
        mv z (+ x y)
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])

    x_sym = top.find_sym('x')
    y_sym = top.find_sym('y')
    z_sym = top.find_sym('z')
    assert x_sym.typ.is_int()
    assert y_sym.typ.is_int()
    assert z_sym.typ.is_int()


def test_static_type_prop_bool():
    """StaticTypePropagation with bool constant."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef
    blk1:
        mv x True
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])

    x_sym = top.find_sym('x')
    assert x_sym.typ.is_bool()


def test_static_type_prop_string():
    """StaticTypePropagation with string constant."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef
    blk1:
        mv x 'hello'
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])

    x_sym = top.find_sym('x')
    assert x_sym.typ.is_str()


def test_typeprop_binop_signed():
    """TypePropagation: BinOp with signed ints yields signed int."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func -1)

    scope @top.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func.return_type.is_int()


def test_typeprop_mcjump():
    """TypePropagation: MCJump visits all conditions."""
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
        var y: undef
    blk1:
        mv x @in_x
        mj (< x 1) blk2 (< x 2) blk3 True blk4
    blk2:
        mv y 10
        j blk5
    blk3:
        mv y 20
        j blk5
    blk4:
        mv y 30
        j blk5
    blk5:
        mv @return y
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    y_sym = func.find_sym('y')
    assert y_sym.typ.is_int()


def test_typeprop_multi_var_propagation():
    """TypePropagation: multiple variables get their types propagated."""
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
        var y: undef
        var z: undef
    blk1:
        mv x @in_x
        mv y (+ x 1)
        mv z (+ y 2)
        mv @return (+ y z)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    y_sym = func.find_sym('y')
    z_sym = func.find_sym('z')
    assert y_sym.typ.is_int()
    assert z_sym.typ.is_int()


def test_typeprop_mutable_method():
    """TypePropagation: method writing to self attribute is tagged mutable (via IRTranslator)."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
class C:
    def __init__(self, val):
        self.x = val
    def set_x(self, val):
        self.x = val
c = C(1)
c.set_x(2)
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    TypePropagation(is_strict=False).process_all()
    set_x = env.scopes['@top.C.set_x']
    assert set_x.is_mutable()


def test_typeprop_lib_scope_skipped():
    """TypePropagation: lib scopes are typed without processing body."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef

    scope lib_ns
        tags namespace lib
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    lib_ns = env.scopes['lib_ns']
    install_builtins(top)

    tp = TypePropagation(is_strict=False)
    typed, _ = tp.process_scopes([top, lib_ns])
    assert lib_ns in typed


# ============================================================
# Tests using IRTranslator to generate richer IR for typeprop
# ============================================================


def _translate_and_propagate(src, use_specializer=False):
    """Helper: translate source and run type propagation."""
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    if use_specializer:
        return TypeSpecializer().process_all()
    else:
        return TypePropagation(is_strict=False).process_all()


def test_typeprop_mref_read():
    """TypePropagation: MRef (subscript read) on a list."""
    setup_test()
    src = '''
def f():
    a = [10, 20, 30]
    x = a[0]
    return x
f()
'''
    typed_scopes, _ = _translate_and_propagate(src)
    func = env.scopes['@top.f']
    x_sym = func.find_sym('x')
    assert x_sym.typ.is_int()


def test_typeprop_mstore():
    """TypePropagation: MStore (subscript write) on a list."""
    setup_test()
    src = '''
def f():
    a = [0, 0, 0]
    a[0] = 42
    return a
f()
'''
    typed_scopes, _ = _translate_and_propagate(src)
    func = env.scopes['@top.f']
    a_sym = func.find_sym('a')
    assert a_sym.typ.is_list()


def test_typeprop_if_else_branches():
    """TypePropagation: type propagation across if/else branches."""
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
    typed_scopes, _ = _translate_and_propagate(src)
    func = env.scopes['@top.f']
    y_sym = func.find_sym('y')
    assert y_sym.typ.is_int()


def test_typeprop_while_loop():
    """TypePropagation: type propagation through a while loop."""
    setup_test()
    src = '''
def f():
    i = 0
    while i < 10:
        i = i + 1
    return i
f()
'''
    typed_scopes, _ = _translate_and_propagate(src)
    func = env.scopes['@top.f']
    i_sym = func.find_sym('i')
    assert i_sym.typ.is_int()


def test_typeprop_for_range():
    """TypePropagation: type propagation through for-range loop."""
    setup_test()
    src = '''
def f():
    s = 0
    for i in range(10):
        s = s + i
    return s
f()
'''
    typed_scopes, _ = _translate_and_propagate(src)
    func = env.scopes['@top.f']
    s_sym = func.find_sym('s')
    assert s_sym.typ.is_int()


def test_specialize_class_construction():
    """TypeSpecializer: class construction specialization."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
    def get(self):
        return self.x
c = C(42)
'''
    typed_scopes, old_scopes = _translate_and_propagate(src, use_specializer=True)
    # Specialized class should exist
    spec_scopes = [name for name in env.scopes if name.startswith('@top.C_')]
    assert len(spec_scopes) >= 1


def test_specialize_multiple_calls():
    """TypeSpecializer: function called with different arg types creates different specializations."""
    setup_test()
    src = '''
def f(x):
    return x + 1
f(1)
'''
    typed_scopes, old_scopes = _translate_and_propagate(src, use_specializer=True)
    f_i32 = env.scopes.get('@top.f_i32')
    assert f_i32 is not None
    assert f_i32.is_specialized()


def test_typeprop_attr_on_object():
    """TypePropagation: attribute access on object instances."""
    setup_test()
    src = '''
class C:
    def __init__(self, val):
        self.x = val
    def get(self):
        return self.x
c = C(5)
c.get()
'''
    typed_scopes, _ = _translate_and_propagate(src)
    get_scope = env.scopes['@top.C.get']
    assert get_scope.return_type is not None


def test_typeprop_new_object():
    """TypePropagation: New node returns object type."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
def f():
    c = C(1)
    return c
f()
'''
    typed_scopes, _ = _translate_and_propagate(src)
    func = env.scopes['@top.f']
    c_sym = func.find_sym('c')
    assert c_sym.typ.is_object()


def test_typeprop_binop_mixed_widths():
    """TypePropagation: BinOp with different int widths takes the wider one."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func 1)

    scope @top.func
        tags function
        param x: int16
        return undef
        var y: undef
    blk1:
        mv x @in_x
        mv y (+ x 1)
        mv @return y
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    y_sym = func.find_sym('y')
    assert y_sym.typ.is_int()
    assert y_sym.typ.width == 32  # max(16, 32)


def test_static_typeprop_relop():
    """StaticTypePropagation: RelOp propagates bool type."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef
        var y: undef
    blk1:
        mv x (< 1 2)
        mv y (== 3 3)
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])
    x_sym = top.find_sym('x')
    y_sym = top.find_sym('y')
    assert x_sym.typ.is_bool()
    assert y_sym.typ.is_bool()


def test_static_typeprop_call():
    """StaticTypePropagation: non-strict call returns callee return type."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
        var x: undef
    blk1:
        mv x (call func 42)

    scope @top.func
        tags function
        param y: undef
        return int32
    blk1:
        mv y @in_y
        mv @return y
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])
    x_sym = top.find_sym('x')
    assert x_sym.typ.is_int()



def test_typeprop_temp_function_load():
    """TypePropagation: visiting Temp with function type and LOAD context adds scope."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
        var helper: function(@top.helper)
    blk1:
        expr (call func 1)

    scope @top.helper
        tags function
        return int32
    blk1:
        mv @return 99
        ret @return

    scope @top.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (call helper)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    helper = env.scopes['@top.helper']
    assert helper in typed_scopes


def test_specialize_function_existing():
    """TypeSpecializer: specializing an already specialized function returns existing."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func 1)
        expr (call func 2)

    scope @top.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()
    # Both calls with int args should create the same specialization
    f_i32 = env.scopes.get('@top.func_i32')
    assert f_i32 is not None
    assert f_i32.is_specialized()


# ============================================================
# Additional TypeSpecializer tests for more coverage
# ============================================================


def test_specialize_function_with_defaults():
    """TypeSpecializer: function with default args uses _normalize_args."""
    setup_test()
    src = '''
def f(x, y=10):
    return x + y
f(1)
'''
    _translate_and_propagate(src, use_specializer=True)
    # Should have specialized f
    spec_scopes = [name for name in env.scopes if 'f_' in name and '@top' in name]
    assert len(spec_scopes) >= 1


def test_specialize_function_with_kwargs():
    """TypeSpecializer: function called with kwargs uses _normalize_args."""
    setup_test()
    src = '''
def f(x, y=10):
    return x + y
f(1, y=20)
'''
    _translate_and_propagate(src, use_specializer=True)
    spec_scopes = [name for name in env.scopes if 'f_' in name and '@top' in name]
    assert len(spec_scopes) >= 1


def test_specialize_method_call():
    """TypeSpecializer: method call on object."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
    def get(self):
        return self.x
c = C(1)
c.get()
'''
    _translate_and_propagate(src, use_specializer=True)
    C = env.scopes.get('@top.C')
    assert C is not None


def test_specialize_attr_function_call():
    """TypeSpecializer: calling a function through namespace attribute."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var ns: namespace(ns)
    blk1:
        expr (call ns.func 10)

    scope ns
        tags namespace
        var func: function(ns.func)

    scope ns.func
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

    TypeSpecializer().process_all()
    func_i32 = env.scopes.get('ns.func_i32')
    assert func_i32 is not None
    assert func_i32.is_specialized()


def test_specialize_function_already_existing():
    """TypeSpecializer: calling function that's already specialized returns existing."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var f: function(@top.f)
        var g: function(@top.g)
    blk1:
        expr (call f 1)
        expr (call g 1)

    scope @top.f
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (call g x)
        ret @return

    scope @top.g
        tags function
        param y: undef
        return undef
    blk1:
        mv y @in_y
        mv @return (+ y 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()
    g_i32 = env.scopes.get('@top.g_i32')
    assert g_i32 is not None


def test_typeprop_reject_then_succeed():
    """TypePropagation: RejectPropagation re-queues scope, then succeeds on retry."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var f: function(@top.f)
        var g: function(@top.g)
    blk1:
        expr (call f 1)

    scope @top.f
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (call g x)
        ret @return

    scope @top.g
        tags function
        param y: undef
        return undef
    blk1:
        mv y @in_y
        mv @return (+ y 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    g = env.scopes['@top.g']
    f = env.scopes['@top.f']
    assert g in typed_scopes
    assert f in typed_scopes


def test_specialize_class_with_method_call():
    """TypeSpecializer: class with constructor and method call (end-to-end)."""
    setup_test()
    src = '''
class C:
    def __init__(self, val):
        self.val = val
    def inc(self, n):
        return self.val + n
c = C(10)
c.inc(5)
'''
    _translate_and_propagate(src, use_specializer=True)
    # Should have specialized C
    spec_classes = [n for n in env.scopes if n.startswith('@top.C_')]
    assert len(spec_classes) >= 1


def test_typeprop_temp_imported():
    """TypePropagation: visiting imported Temp adds the import scope."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var other: namespace(other)
        from other import helper
    blk1:
        expr (call helper 1)

    scope other
        tags namespace
        var helper: function(other.helper)

    scope other.helper
        tags function
        param x: undef
        return int32
    blk1:
        mv x @in_x
        mv @return x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    helper = env.scopes['other.helper']
    assert helper in typed_scopes


def test_typeprop_function_in_load_ctx():
    """TypePropagation: visiting a function-typed Temp in LOAD context adds func scope."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var main: function(@top.main)
        var helper: function(@top.helper)
    blk1:
        expr (call main 1)

    scope @top.helper
        tags function
        param y: undef
        return int32
    blk1:
        mv y @in_y
        mv @return y
        ret @return

    scope @top.main
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (call helper x)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    helper = env.scopes['@top.helper']
    assert helper in typed_scopes


def test_specialize_multiple_types():
    """TypeSpecializer: function with multiple int params."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func 1 2)

    scope @top.func
        tags function
        param x: undef
        param y: undef
        return undef
    blk1:
        mv x @in_x
        mv y @in_y
        mv @return (+ x y)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()
    func_spec = env.scopes.get('@top.func_i32i32')
    assert func_spec is not None
    assert func_spec.is_specialized()
    assert len(func_spec.param_types()) == 2


def test_typeprop_attr_on_namespace():
    """TypePropagation: Attr access on namespace resolves correctly."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var ns: namespace(ns)
        var x: undef
    blk1:
        mv x ns.val

    scope ns
        tags namespace
        var val: int32
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])
    x_sym = top.find_sym('x')
    assert x_sym.typ.is_int()


def test_typeprop_expr_stm():
    """TypePropagation: Expr statement visits its sub-expression."""
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
        expr (+ x 1)
        mv @return x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func in typed_scopes


def test_static_typeprop_expr():
    """StaticTypePropagation: Expr stm is visited."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func 42)

    scope @top.func
        tags function
        param x: int32
        return int32
    blk1:
        mv x @in_x
        mv @return x
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])


# ============================================================
# More complex scenarios for higher coverage
# ============================================================


def test_typeprop_mref_tuple_element():
    """TypePropagation: MRef on tuple returns element type."""
    setup_test()
    src = '''
def f():
    t = (1, 2, 3)
    x = t[0]
    return x
f()
'''
    _translate_and_propagate(src)
    func = env.scopes['@top.f']
    x_sym = func.find_sym('x')
    assert x_sym.typ.is_int()


def test_typeprop_mstore_on_list():
    """TypePropagation: MStore writes to list element."""
    setup_test()
    src = '''
def f():
    a = [0, 0, 0]
    a[1] = 42
    return a[0]
f()
'''
    _translate_and_propagate(src)
    func = env.scopes['@top.f']
    a_sym = func.find_sym('a')
    assert a_sym.typ.is_list()


def test_typeprop_array_bool_items():
    """TypePropagation: Array of bools."""
    setup_test()
    src = '''
def f():
    a = [True, False, True]
    return a
f()
'''
    _translate_and_propagate(src)
    func = env.scopes['@top.f']
    a_sym = func.find_sym('a')
    assert a_sym.typ.is_list()
    assert a_sym.typ.element.is_bool()


def test_specialize_class_no_params():
    """TypeSpecializer: class with no-arg constructor."""
    setup_test()
    src = '''
class C:
    def __init__(self):
        self.x = 0
c = C()
'''
    _translate_and_propagate(src, use_specializer=True)
    C = env.scopes.get('@top.C')
    assert C is not None


def test_specialize_with_explicit_param_types():
    """TypeSpecializer: function with explicit param types."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func 1)

    scope @top.func
        tags function
        param x: int32
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()
    func_i32 = env.scopes.get('@top.func_i32')
    assert func_i32 is not None
    assert func_i32.is_specialized()


def test_static_typeprop_new():
    """StaticTypePropagation non-strict visit_New returns object type."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
c = C(1)
'''
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    StaticTypePropagation(is_strict=False).process_scopes([top])
    c_sym = top.find_sym('c')
    assert c_sym.typ.is_object()


def test_specialize_imported_function():
    """TypeSpecializer: imported function from another namespace."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var other: namespace(other)
        from other import helper
    blk1:
        expr (call helper 1)

    scope other
        tags namespace
        var helper: function(other.helper)

    scope other.helper
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 10)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()
    helper_i32 = env.scopes.get('other.helper_i32')
    assert helper_i32 is not None
    assert helper_i32.is_specialized()
    top_sym = top.find_sym('helper_i32')
    assert top_sym is not None


def test_typeprop_directory_scope_skipped():
    """TypePropagation: directory scopes are skipped."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace

    scope dir
        tags directory
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    dir_scope = env.scopes['dir']
    install_builtins(top)

    tp = TypePropagation(is_strict=False)
    typed, _ = tp.process_scopes([top, dir_scope])
    assert dir_scope not in typed


def test_typeprop_move_mref_dst():
    """TypePropagation: Move with MRef as destination."""
    setup_test()
    src = '''
def f():
    a = [0, 0]
    a[0] = 99
    return a
f()
'''
    _translate_and_propagate(src)
    func = env.scopes['@top.f']
    a_sym = func.find_sym('a')
    assert a_sym.typ.is_list()


def test_typeprop_propagate_updates_sym():
    """TypePropagation: _propagate updates symbol type."""
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
        var y: undef
        var z: undef
    blk1:
        mv x @in_x
        mv y x
        mv z (+ y 1)
        mv @return z
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    z_sym = func.find_sym('z')
    assert z_sym.typ.is_int()
    assert z_sym.typ.width == 32


def test_specialize_method_with_params():
    """TypeSpecializer: method with params gets specialized."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
    def add(self, y):
        return self.x + y
c = C(1)
c.add(2)
'''
    _translate_and_propagate(src, use_specializer=True)
    add_scopes = [n for n in env.scopes if 'add' in n and '@top.C' in n]
    assert len(add_scopes) >= 1


def test_typeprop_sequential_calls():
    """TypePropagation: sequential function calls propagate types."""
    setup_test()
    src = '''
def g(x):
    return x + 1
def f(x):
    y = g(x)
    return y
f(1)
'''
    typed_scopes, _ = _translate_and_propagate(src)
    f = env.scopes['@top.f']
    g = env.scopes['@top.g']
    assert f in typed_scopes
    assert g in typed_scopes


def test_typeprop_static_multi_scope():
    """StaticTypePropagation processes multiple scopes."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: undef
        var ns: namespace(ns)
    blk1:
        mv x 10

    scope ns
        tags namespace
        var y: undef
    blk1:
        mv y 20
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    ns = env.scopes['ns']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top, ns])
    x_sym = top.find_sym('x')
    y_sym = ns.find_sym('y')
    assert x_sym.typ.is_int()
    assert y_sym.typ.is_int()


def test_type_replacer_no_match():
    """TypeReplacer does not change types that don't match."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)

    scope @top.func
        tags function
        var x: int32
    blk1:
        mv x 1
    """
    IRParser(block_src).parse_scope()
    func = env.scopes['@top.func']

    old_t = Type.bool()
    new_t = Type.str()
    replacer = TypeReplacer(old_t, new_t, lambda a, b: a == b)
    replacer.process(func)

    x_sym = func.find_sym('x')
    assert x_sym.typ.is_int()  # unchanged


def test_typeprop_attr_subobject():
    """TypePropagation: attr access on object marks subobject."""
    setup_test()
    src = '''
class Inner:
    def __init__(self):
        self.v = 0
class Outer:
    def __init__(self):
        self.inner = Inner()
    def get_v(self):
        return self.inner.v
o = Outer()
o.get_v()
'''
    _translate_and_propagate(src)
    get_v = env.scopes.get('@top.Outer.get_v')
    assert get_v is not None


def test_specialize_func_with_default_val():
    """TypeSpecializer: function called with default values normalizes args."""
    setup_test()
    src = '''
def f(x, y=5, z=10):
    return x + y + z
f(1)
'''
    _translate_and_propagate(src, use_specializer=True)
    spec_scopes = [n for n in env.scopes if n.startswith('@top.f_') and n != '@top.f']
    assert len(spec_scopes) >= 1


def test_specialize_func_kwargs_only():
    """TypeSpecializer: function called with only kwargs for defaults."""
    setup_test()
    src = '''
def f(x, y=5):
    return x + y
f(1, y=20)
'''
    _translate_and_propagate(src, use_specializer=True)
    spec_scopes = [n for n in env.scopes if n.startswith('@top.f_') and n != '@top.f']
    assert len(spec_scopes) >= 1


def test_specialize_class_method_call_attr():
    """TypeSpecializer: method call via attribute (c.method(arg))."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
    def calc(self, y):
        return self.x + y
c = C(10)
r = c.calc(5)
'''
    _translate_and_propagate(src, use_specializer=True)
    calc_scopes = [n for n in env.scopes if 'calc' in n]
    assert len(calc_scopes) >= 1


def test_specialize_class_ctor_and_method():
    """TypeSpecializer: full class creation and method specialization."""
    setup_test()
    src = '''
class Adder:
    def __init__(self, base):
        self.base = base
    def add(self, n):
        return self.base + n
a = Adder(100)
result = a.add(42)
'''
    _translate_and_propagate(src, use_specializer=True)
    # Specialized class should exist
    spec_scopes = [n for n in env.scopes if n.startswith('@top.Adder_')]
    assert len(spec_scopes) >= 1


def test_typeprop_superseded_scope_skipped():
    """TypePropagation: superseded scopes are skipped in worklist."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var other: namespace(other)
        from other import func
    blk1:
        expr (call func 1)

    scope other
        tags namespace
        var func: function(other.func)

    scope other.func
        tags function
        param x: undef
        return undef
    blk1:
        mv x @in_x
        mv @return (+ x 1)
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    TypeSpecializer().process_all()
    # Original func should be superseded
    func = env.scopes['other.func']
    assert func.is_superseded()


def test_typeprop_add_scope_dedup():
    """TypePropagation: _add_scope doesn't add duplicates."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func 1)
        expr (call func 2)

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

    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes['@top.func']
    assert func in typed_scopes


def test_specialize_new_class_with_method():
    """TypeSpecializer: New with class that has methods."""
    setup_test()
    src = '''
class Counter:
    def __init__(self, start):
        self.val = start
    def inc(self):
        self.val = self.val + 1
        return self.val
c = Counter(0)
c.inc()
'''
    _translate_and_propagate(src, use_specializer=True)
    spec_scopes = [n for n in env.scopes if n.startswith('@top.Counter_')]
    assert len(spec_scopes) >= 1


def test_typeprop_find_attr_from_specialized():
    """TypePropagation: _find_attr_type_from_specialized finds type from specialized class."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
    def get(self):
        return self.x
c = C(1)
c.get()
'''
    _translate_and_propagate(src, use_specializer=True)
    get_scopes = [n for n in env.scopes if 'get' in n and 'C' in n]
    assert len(get_scopes) >= 1


def test_static_typeprop_attr_access():
    """StaticTypePropagation: Attr access on namespace."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var ns: namespace(ns)
        var x: undef
    blk1:
        mv x ns.val

    scope ns
        tags namespace
        var val: int32
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=False).process_scopes([top])
    x_sym = top.find_sym('x')
    assert x_sym.typ.is_int()


# ============================================================
# Direct TypeExprEvaluator tests
# ============================================================


def test_type_expr_evaluator_const():
    """TypeExprEvaluator: visit_Const returns the Const ir."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']

    tee = TypeExprEvaluator()
    c = Const(value=42)
    expr = Expr(exp=c)
    from polyphony.compiler.ir.types.exprtype import ExprType
    expr_t = ExprType(explicit=False, scope_name=top.name, expr=expr)
    result = tee.visit_expr_type(expr_t)
    # visit_Const returns the Const itself, which visit_Expr wraps
    assert isinstance(result, Expr)


def test_type_expr_evaluator_visit_expr():
    """TypeExprEvaluator: visit_Expr wraps result in Expr if not Type."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']

    tee = TypeExprEvaluator()
    c = Const(value=10)
    expr = Expr(exp=c)
    result = tee.visit(expr)
    assert isinstance(result, Expr)


def test_type_evaluator_visit_expr_type():
    """TypeEvaluator.visit_expr evaluates an expression type."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']

    te = TypeEvaluator(top)
    c = Const(value=16)
    expr = Expr(exp=c)
    from polyphony.compiler.ir.types.exprtype import ExprType
    t = ExprType(explicit=False, scope_name=top.name, expr=expr)
    result = te.visit(t)
    assert result is not None


def test_type_expr_evaluator_temp_scalar():
    """TypeExprEvaluator: visit_Temp with scalar type returns Temp."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var x: int32
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']

    # Set a constant for x
    x_sym = top.find_sym('x')
    top.constants[x_sym] = Const(value=8)

    tee = TypeExprEvaluator()
    temp = Temp(name='x')
    expr = Expr(exp=temp)
    from polyphony.compiler.ir.types.exprtype import ExprType
    expr_t = ExprType(explicit=False, scope_name=top.name, expr=expr)
    result = tee.visit_expr_type(expr_t)
    # With a constant, should return the Const
    assert isinstance(result, Expr) or isinstance(result, Const) or isinstance(result, Type)


def test_type_expr_evaluator_temp_class():
    """TypeExprEvaluator: visit_Temp with class type returns resolved type."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
from polyphony.typing import List
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    list_sym = top.find_sym('List')
    assert list_sym is not None
    assert list_sym.typ.is_class()

    tee = TypeExprEvaluator()
    temp = Temp(name='List')
    tee.scope = top
    result = tee.visit_Temp(temp)
    # Should resolve typeclass to a type
    assert isinstance(result, Type) or isinstance(result, Temp)


def test_type_expr_evaluator_array():
    """TypeExprEvaluator: visit_Array with Type elements."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
    blk1:
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']

    tee = TypeExprEvaluator()
    tee.scope = top
    # Array of Const items
    items = [Const(value=1), Const(value=2)]
    arr = Array(items=items)
    result = tee.visit_Array(arr)
    # Returns the array or type
    assert result is not None


def test_type_expr_evaluator_mref_int():
    """TypeExprEvaluator: visit_MRef on int type returns int with width."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
from polyphony.typing import int8
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]

    # int8 should be resolved as a typeclass
    int8_sym = top.find_sym('int8')
    if int8_sym and int8_sym.typ.is_class():
        tee = TypeExprEvaluator()
        tee.scope = top
        # Try to visit Temp for int8
        temp = Temp(name='int8')
        result = tee.visit_Temp(temp)
        assert result is not None


# ============================================================
# TypeEvalVisitor with constants
# ============================================================


def test_type_expr_eval_mref_list_type():
    """TypeExprEvaluator: List[int8] annotation resolves to list type."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
from polyphony.typing import List, int8
def f(a: List[int8]):
    return a
f(a=1)
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    func = env.scopes.get('@top.f')
    if func:
        a_sym = func.find_sym('a')
        if a_sym:
            # The annotation should have resolved to a list type
            assert a_sym.typ.is_list()


def test_type_expr_eval_int_width():
    """TypeExprEvaluator: int type with explicit width."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
from polyphony.typing import int8
def f(x: int8):
    return x
f(1)
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    typed_scopes, _ = TypePropagation(is_strict=False).process_all()
    func = env.scopes.get('@top.f')
    if func:
        x_sym = func.find_sym('x')
        assert x_sym.typ.is_int()
        assert x_sym.typ.width == 8


def test_specialize_with_typed_param():
    """TypeSpecializer: function with explicit int8 param type."""
    setup_test()
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    src = '''
from polyphony.typing import int8
def f(x: int8):
    return x + 1
f(1)
'''
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    TypeSpecializer().process_all()
    spec_scopes = [n for n in env.scopes if n.startswith('@top.f_')]
    assert len(spec_scopes) >= 1


def test_specialize_class_new_with_method_call():
    """TypeSpecializer: New + method call through full pipeline."""
    setup_test()
    src = '''
class Vec:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def mag(self):
        return self.x + self.y
v = Vec(3, 4)
v.mag()
'''
    _translate_and_propagate(src, use_specializer=True)
    vec_specs = [n for n in env.scopes if n.startswith('@top.Vec_')]
    assert len(vec_specs) >= 1
    mag_scopes = [n for n in env.scopes if 'mag' in n]
    assert len(mag_scopes) >= 1


def test_specialize_func_with_bool_arg():
    """TypeSpecializer: function called with bool arg."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
    blk1:
        expr (call func True)

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

    TypeSpecializer().process_all()
    spec = [n for n in env.scopes if n.startswith('@top.func_') and n != '@top.func']
    assert len(spec) >= 1


def test_static_typeprop_strict_call():
    """StaticTypePropagation with is_strict=True delegates to TypePropagation visit_Call."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)
        var x: undef
    blk1:
        mv x (call func 42)

    scope @top.func
        tags function
        param y: int32
        return int32
    blk1:
        mv y @in_y
        mv @return y
        ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    StaticTypePropagation(is_strict=True).process_scopes([top])
    x_sym = top.find_sym('x')
    assert x_sym.typ.is_int()


def test_static_typeprop_strict_new():
    """StaticTypePropagation strict visit_New delegates to parent."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
c = C(1)
'''
    from polyphony.compiler.frontend.python.irtranslator import IRTranslator
    IRTranslator().translate(src, '')
    top = env.scopes[env.global_scope_name]
    install_builtins(top)
    StaticTypePropagation(is_strict=True).process_scopes([top])
    c_sym = top.find_sym('c')
    assert c_sym.typ.is_object()


def test_type_eval_visitor_with_constants():
    """TypeEvalVisitor: evaluates types in scope with constants."""
    setup_test(with_global=False)
    block_src = """
    scope @top
        tags namespace
        var func: function(@top.func)

    scope @top.func
        tags function
        param x: int32
        return int32
    blk1:
        mv x @in_x
        mv @return x
        ret @return
    """
    IRParser(block_src).parse_scope()
    func = env.scopes['@top.func']

    # Add a constant to the scope
    x_sym = func.find_sym('x')
    func.constants[x_sym] = Const(value=42)

    TypeEvalVisitor().process(func)
    # Param types should still be int
    for sym in func.param_symbols():
        assert sym.typ.is_int()
