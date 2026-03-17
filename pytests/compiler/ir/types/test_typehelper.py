"""Tests for polyphony.compiler.ir.types.typehelper (type_to_scope, find_expr, replace_type_dict)."""
import pytest
from pytests.compiler.base import setup_test
from polyphony.compiler.common.env import env
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.types.typehelper import (
    type_from_ir,
    type_to_scope,
    find_expr,
    replace_type_dict,
    type_from_typeclass,
)
from polyphony.compiler.ir.ir import Expr, Const, Temp, Attr, MRef, Array, BinOp
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.block import Block


# ---- type_to_scope ----

class TestTypeToScope:
    def test_int(self):
        setup_test()
        scope = type_to_scope(Type.int(32))
        assert scope.name == '__builtin__.int'

    def test_bool(self):
        setup_test()
        scope = type_to_scope(Type.bool())
        assert scope.name == '__builtin__.bool'

    def test_str(self):
        setup_test()
        scope = type_to_scope(Type.str())
        assert scope.name == '__builtin__.str'

    def test_list(self):
        setup_test()
        scope = type_to_scope(Type.list(Type.int()))
        assert scope.name == '__builtin__.list'

    def test_tuple(self):
        setup_test()
        scope = type_to_scope(Type.tuple(Type.int(), 3))
        assert scope.name == '__builtin__.tuple'

    def test_object(self):
        setup_test()
        scope = type_to_scope(Type.object(env.scopes['__builtin__.object']))
        assert scope.name == '__builtin__.object'

    def test_unsupported_raises(self):
        setup_test()
        with pytest.raises(AssertionError):
            type_to_scope(Type.none())


# ---- find_expr ----

class TestFindExpr:
    def test_non_type_returns_empty(self):
        assert find_expr("not a type") == []
        assert find_expr(42) == []
        assert find_expr(None) == []

    def test_scalar_returns_empty(self):
        setup_test()
        assert find_expr(Type.int()) == []
        assert find_expr(Type.bool()) == []
        assert find_expr(Type.str()) == []
        assert find_expr(Type.none()) == []
        assert find_expr(Type.undef()) == []

    def test_expr_type(self):
        setup_test()
        expr_t = Type.expr(Expr(Const(1)), env.scopes['__builtin__'])
        result = find_expr(expr_t)
        assert len(result) == 1
        assert result[0] is expr_t

    def test_list_with_expr_element(self):
        setup_test()
        expr_t = Type.expr(Expr(Const(1)), env.scopes['__builtin__'])
        list_t = Type.list(expr_t, 10)
        result = find_expr(list_t)
        assert len(result) == 1
        assert result[0] is expr_t

    def test_list_with_expr_length(self):
        setup_test()
        expr_len = Type.expr(Expr(Temp('N')), env.scopes['__builtin__'])
        list_t = Type.list(Type.int(), expr_len)
        result = find_expr(list_t)
        assert len(result) == 1
        assert result[0] is expr_len

    def test_list_with_both_expr(self):
        setup_test()
        expr_elm = Type.expr(Expr(Const(1)), env.scopes['__builtin__'])
        expr_len = Type.expr(Expr(Temp('N')), env.scopes['__builtin__'])
        list_t = Type.list(expr_elm, expr_len)
        result = find_expr(list_t)
        assert len(result) == 2

    def test_tuple_with_expr_element(self):
        setup_test()
        expr_t = Type.expr(Expr(Const(1)), env.scopes['__builtin__'])
        tuple_t = Type.tuple(expr_t, 3)
        result = find_expr(tuple_t)
        assert len(result) == 1
        assert result[0] is expr_t

    def test_function_with_expr_params(self):
        setup_test()
        from polyphony.compiler.ir.scope import Scope
        from polyphony.compiler.ir.block import Block

        top = Scope.create(None, 'ftop', {'namespace'})
        F = Scope.create(top, 'func', {'function'})
        top.add_sym('func', set(), typ=Type.function(F))
        blk = Block(F)
        F.set_entry_block(blk)
        F.set_exit_block(blk)

        expr_param = Type.expr(Expr(Const(1)), env.scopes['__builtin__'])
        expr_ret = Type.expr(Expr(Temp('x')), env.scopes['__builtin__'])
        func_t = Type.function(F, ret_t=expr_ret, param_ts=[Type.int(), expr_param])
        result = find_expr(func_t)
        assert len(result) == 2

    def test_object_returns_empty(self):
        setup_test()
        obj_t = Type.object(env.scopes['__builtin__.object'])
        assert find_expr(obj_t) == []

    def test_list_no_expr(self):
        setup_test()
        list_t = Type.list(Type.int(), 10)
        assert find_expr(list_t) == []


# ---- replace_type_dict ----

class TestReplaceTypeDict:
    def test_simple_replacement(self):
        dic = {'scope_name': 'old_scope', 'explicit': True}
        new_dic = {}
        value_map = {'old_scope': 'new_scope'}
        result = replace_type_dict(dic, new_dic, 'scope_name', value_map)
        assert result is True
        assert new_dic['scope_name'] == 'new_scope'
        assert new_dic['explicit'] is True

    def test_no_match(self):
        dic = {'scope_name': 'other', 'explicit': True}
        new_dic = {}
        value_map = {'old_scope': 'new_scope'}
        result = replace_type_dict(dic, new_dic, 'scope_name', value_map)
        assert result is False
        assert new_dic['scope_name'] == 'other'

    def test_nested_dict(self):
        dic = {
            'element': {
                'scope_name': 'old_scope',
                'width': 32,
            },
            'length': 10,
        }
        new_dic = {}
        value_map = {'old_scope': 'new_scope'}
        result = replace_type_dict(dic, new_dic, 'scope_name', value_map)
        assert result is True
        assert new_dic['element']['scope_name'] == 'new_scope'
        assert new_dic['element']['width'] == 32
        assert new_dic['length'] == 10

    def test_list_value_with_replacement(self):
        """List elements matching key AND in value_map are replaced."""
        dic = {
            'names': ['scope_name', 'keep', 'other'],
        }
        new_dic = {}
        value_map = {'scope_name': 'new_scope'}
        # key='scope_name' matches list element 'scope_name'
        result = replace_type_dict(dic, new_dic, 'scope_name', value_map)
        assert result is True
        assert new_dic['names'] == ['new_scope', 'keep', 'other']
        assert isinstance(new_dic['names'], list)

    def test_tuple_value_with_replacement(self):
        dic = {
            'names': ('scope_name', 'keep'),
        }
        new_dic = {}
        value_map = {'scope_name': 'new_scope'}
        result = replace_type_dict(dic, new_dic, 'scope_name', value_map)
        assert result is True
        assert new_dic['names'] == ('new_scope', 'keep')
        assert isinstance(new_dic['names'], tuple)

    def test_list_with_nested_dict(self):
        dic = {
            'params': [
                {'scope_name': 'old_scope', 'width': 8},
                {'scope_name': 'keep', 'width': 16},
            ],
        }
        new_dic = {}
        value_map = {'old_scope': 'new_scope'}
        result = replace_type_dict(dic, new_dic, 'scope_name', value_map)
        assert result is True
        assert new_dic['params'][0]['scope_name'] == 'new_scope'
        assert new_dic['params'][1]['scope_name'] == 'keep'

    def test_no_replacement_in_list(self):
        dic = {'items': ['a', 'b']}
        new_dic = {}
        value_map = {'x': 'y'}
        result = replace_type_dict(dic, new_dic, 'items', value_map)
        assert result is False
        assert new_dic['items'] == ['a', 'b']

    def test_deeply_nested(self):
        dic = {
            'outer': {
                'inner': {
                    'scope_name': 'deep_old',
                },
            },
        }
        new_dic = {}
        value_map = {'deep_old': 'deep_new'}
        result = replace_type_dict(dic, new_dic, 'scope_name', value_map)
        assert result is True
        assert new_dic['outer']['inner']['scope_name'] == 'deep_new'


# ---- type_from_typeclass additional coverage ----

class TestTypeFromTypeclassExtra:
    def test_builtin_type(self):
        """type_from_typeclass for __builtin__.type."""
        setup_test()
        typecls = env.scopes['__builtin__.type']
        t = type_from_typeclass(typecls)
        assert t.is_class()

    def test_polyphony_typing_Int(self):
        """type_from_typeclass for polyphony.typing.Int."""
        setup_test()
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        translator = IRTranslator()
        translator.translate('import polyphony.typing', '')

        Int_scope = env.scopes.get('polyphony.typing.Int')
        if Int_scope:
            t = type_from_typeclass(Int_scope)
            assert t.is_int()

    def test_polyphony_typing_List(self):
        """type_from_typeclass for polyphony.typing.List."""
        setup_test()
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        translator = IRTranslator()
        translator.translate('import polyphony.typing', '')

        List_scope = env.scopes.get('polyphony.typing.List')
        if List_scope:
            t = type_from_typeclass(List_scope)
            assert t.is_list()

    def test_polyphony_typing_Tuple(self):
        """type_from_typeclass for polyphony.typing.Tuple."""
        setup_test()
        from polyphony.compiler.frontend.python.irtranslator import IRTranslator
        translator = IRTranslator()
        translator.translate('import polyphony.typing', '')

        Tuple_scope = env.scopes.get('polyphony.typing.Tuple')
        if Tuple_scope:
            t = type_from_typeclass(Tuple_scope)
            assert t.is_tuple()


# ---- type_from_ir / _type_from_new_ir additional branch coverage ----

def _new_scope(parent, name, tags):
    """Helper to create a scope for tests."""
    scope = Scope.create(parent, name, tags)
    if parent:
        if 'class' in tags or 'typeclass' in tags:
            parent.add_sym(name, set(), typ=Type.klass(scope, True))
        elif 'function' in tags:
            parent.add_sym(name, set(), typ=Type.function(scope, True))
    blk = Block(scope)
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)
    return scope


class TestTypeFromNewIrBranches:
    def test_attr_non_scope_sym(self):
        """Attr where the resolved symbol has no scope type -> ExprType."""
        setup_test()
        top = env.scopes['@top']
        # Add a non-scope typed symbol 'ns' with int type
        top.add_sym('ns', set(), typ=Type.int())
        # Attr(Temp('ns'), 'val') - ns is int so qsyms[-1] won't have scope
        ir = Attr(Temp('ns'), 'val')
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_expr()

    def test_attr_class_object_non_builtin(self):
        """Attr where sym type is class, scope is object, not builtin -> ExprType + typevar tag."""
        setup_test()
        top = env.scopes['@top']
        C = _new_scope(top, 'Container', {'class'})
        C_instance = C.instantiate('1')
        # Add a symbol 'T' in Container with type class(object) and non-builtin
        C.add_sym('T', set(), typ=Type.klass(env.scopes['__builtin__.object']))
        # ns has type object(Container)
        top.add_sym('cobj', set(), typ=Type.object(C_instance))
        ir = Attr(Temp('cobj'), 'T')
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_expr()

    def test_mref_int_width(self):
        """MRef(int_type_temp, Const(width)) -> IntType with specified width."""
        setup_test()
        top = env.scopes['@top']
        # x: int[16] => MRef(Temp('int'), Const(16))
        ir = MRef(Temp('int'), Const(16))
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_int()
        assert t.width == 16

    def test_array_ir(self):
        """Array IR with single item -> delegates to inner type."""
        setup_test()
        top = env.scopes['@top']
        ir = Array(items=[Temp('int')], mutable=False)
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_int()

    def test_binop_as_irexp(self):
        """BinOp (an IrExp) used as type annotation -> ExprType."""
        setup_test()
        top = env.scopes['@top']
        top.add_sym('a', set(), typ=Type.int())
        top.add_sym('b', set(), typ=Type.int())
        ir = BinOp('Add', Temp('a'), Temp('b'))
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_expr()

    def test_mref_nested_with_size_expr(self):
        """MRef(MRef(list, int), Temp(SIZE)) -> list with expr length."""
        setup_test()
        top = env.scopes['@top']
        top.add_sym('SIZE', set(), typ=Type.int())
        inner = MRef(Temp('list'), Temp('int'))
        ir = MRef(inner, Temp('SIZE'))
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_list()
        assert t.length.is_expr()

    def test_mref_class_with_object_offset(self):
        """MRef(Temp('type'), Temp('SomeClass')) where SomeClass resolves to object type.
        type -> klass(__builtin__.type) -> is_class=True -> line 94 branch."""
        setup_test()
        top = env.scopes['@top']
        D = _new_scope(top, 'SpecD', {'class'})
        D_instance = D.instantiate('1')
        top.add_sym('d_inst', set(), typ=Type.object(D_instance))
        # MRef(Temp('type'), Temp('d_inst')) where type -> ClassType, d_inst -> ObjectType
        ir = MRef(Temp('type'), Temp('d_inst'))
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_class()

    def test_mref_class_with_int_offset(self):
        """MRef(Temp('type'), Temp('int')) -> class type via type_to_scope."""
        setup_test()
        top = env.scopes['@top']
        # type -> ClassType, int -> IntType (not object) -> type_to_scope branch (line 99)
        ir = MRef(Temp('type'), Temp('int'))
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_class()

    def test_temp_non_scope_type_becomes_expr(self):
        """Temp where symbol has non-scope type -> ExprType with typevar tag."""
        setup_test()
        top = env.scopes['@top']
        top.add_sym('myvar', set(), typ=Type.int())
        ir = Temp('myvar')
        t = type_from_ir(top, ir, explicit=True)
        assert t.is_expr()
        # Check typevar tag was added
        sym = top.find_sym('myvar')
        assert 'typevar' in sym.tags
