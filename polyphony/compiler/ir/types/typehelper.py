from __future__ import annotations
from typing import cast, TYPE_CHECKING
from ...common.env import env
from ..irhelper import qualified_symbols
from ...common.env import env
from .type import Type
if TYPE_CHECKING:
    from ..scope import Scope
    from ..ir import IR, EXPR


def type_from_ir(scope: Scope, ir: IR, explicit=False) -> Type:
    '''
    Interpret and return the type of variable expressed by IR
    Examples: 
        source:     'a: int'
        annotation: TEMP('int')
        result:     Type.int()

        source:     'a: Int[s1 + s2]'
        annotation: MREF(TEMP('Int"), BINOP('Add', TEMP('s1'), TEMP('s2')))
        result:     Type.expr(MREF(TEMP('Int"), BINOP('Add', TEMP('s1'), TEMP('s2'))))
    '''
    from ..ir import IR, IRExp, CONST, TEMP, ATTR, MREF, ARRAY, EXPR
    from ..symbol import Symbol
    
    assert ir
    assert isinstance(ir, IR)
    t = None
    if ir.is_a(CONST):
        c = cast(CONST, ir)
        if c.value is None:
            t = Type.none(explicit)
        else:
            t = Type.expr(EXPR(ir))
    elif ir.is_a(TEMP):
        temp = cast(TEMP, ir)
        temp_sym = scope.find_sym(temp.name)
        assert isinstance(temp_sym, Symbol)
        assert temp._sym is temp_sym  # TODO: remove this line
        if temp_sym.typ.has_scope():
            sym_type = temp_sym.typ
            scope = sym_type.scope
            if sym_type.is_class() and scope.is_object() and not temp_sym.is_builtin():
                # ir is a typevar (ex. dtype)
                t = Type.expr(EXPR(temp))
            elif scope.is_typeclass():
                if scope.name == '__builtin__.type':
                    t = Type.klass(env.scopes['__builtin__.object'], explicit=explicit)
                else:
                    t = type_from_typeclass(scope, explicit=explicit)
            else:
                t = Type.object(scope, explicit)
        else:
            t = Type.expr(EXPR(ir))
    elif ir.is_a(ATTR):
        attr = cast(ATTR, ir)
        qsyms = qualified_symbols(attr, scope)
        if isinstance(qsyms[-1], Symbol) and qsyms[-1].typ.has_scope():
            attr_type = qsyms[-1].typ
            scope = attr_type.scope
            if attr_type.is_class() and scope.is_object() and not attr.symbol.is_builtin():
                # ir is a typevar (ex. dtype)
                t = Type.expr(EXPR(attr))
            elif scope.is_typeclass():
                t = type_from_typeclass(scope, explicit=explicit)
            else:
                t = Type.object(scope, explicit)
        else:
            t = Type.expr(EXPR(ir))
    elif ir.is_a(MREF):
        mref = cast(MREF, ir)
        if mref.mem.is_a(MREF):
            t = type_from_ir(scope, mref.mem, explicit)
            if mref.offset.is_a(CONST):
                t = t.clone(length=mref.offset.value)
            else:
                t = t.clone(length=type_from_ir(scope, mref.offset, explicit))
        else:
            t = type_from_ir(scope, mref.mem, explicit)
            if t.is_int():
                assert mref.offset.is_a(CONST)
                t = t.clone(width=mref.offset.value)
            elif t.is_seq():
                t = t.clone(element=type_from_ir(scope, mref.offset, explicit))
            elif t.is_class():
                elm_t = type_from_ir(scope, mref.offset, explicit)
                if elm_t.is_object():
                    t = t.clone(scope=elm_t.scope)
                else:
                    type_scope = type_to_scope(elm_t)
                    t = t.clone(scope=type_scope)
    elif ir.is_a(ARRAY):
        array = cast(ARRAY, ir)
        assert array.repeat.is_a(CONST) and array.repeat.value == 1
        assert array.is_mutable is False
        # FIXME: tuple should have more than one type
        return type_from_ir(scope, array.items[0], explicit)
    else:
        assert ir.is_a(IRExp)
        assert explicit is True
        t = Type.expr(EXPR(ir))
    
    assert t is not None
    t = t.clone(explicit=explicit)
    return t


def type_from_typeclass(scope: Scope, explicit=True) -> Type:
    assert scope.is_typeclass()
    assert scope.parent
    if scope.parent.name == '__builtin__':
        if scope.base_name == 'int':
            return Type.int(explicit=explicit)
        elif scope.base_name == 'bool':
            return Type.bool(explicit=explicit)
        elif scope.base_name == 'object':
            return Type.object(env.scopes['__builtin__.object'], explicit=explicit)
        elif scope.base_name == 'function':
            return Type.function(env.scopes['__builtin__.object'], explicit=explicit)
        elif scope.base_name == 'str':
            return Type.str(explicit=explicit)
        elif scope.base_name == 'list':
            return Type.list(Type.undef(), explicit=explicit)
        elif scope.base_name == 'tuple':
            return Type.tuple(Type.undef(), Type.ANY_LENGTH, explicit=explicit)
        else:
            assert False
    elif scope.parent.name == 'polyphony.typing':
        if scope.base_name.startswith('int'):
            return Type.int(int(scope.base_name[3:]), explicit=explicit)
        elif scope.base_name.startswith('uint'):
            return Type.int(int(scope.base_name[4:]), signed=False, explicit=explicit)
        elif scope.base_name.startswith('bit'):
            if scope.base_name == 'bit':
                return Type.int(1, signed=False, explicit=explicit)
            else:
                return Type.int(int(scope.base_name[3:]), signed=False, explicit=explicit)
        elif scope.base_name == ('Int'):
            return Type.int(explicit=explicit)
        elif scope.base_name == ('List'):
            return Type.list(Type.undef(), explicit=explicit)
        elif scope.base_name == ('Tuple'):
            return Type.tuple(Type.undef(), Type.ANY_LENGTH, explicit=explicit)
        else:
            assert False
    else:
        print(scope.name)
        assert False


def type_to_scope(t: Type) -> Scope:
    from .inttype import IntType
    from .booltype import BoolType
    from .strtype import StrType

    if t.is_int():
        return cast(IntType, t).scope
    elif t.is_bool():
        return cast(BoolType, t).scope
    elif t.is_str():
        return cast(StrType, t).scope
    elif t.is_list():
        scope = env.scopes['__builtin__.list']
    elif t.is_tuple():
        scope = env.scopes['__builtin__.tuple']
    elif t.is_object():
        scope = env.scopes['__builtin__.object']
    else:
        assert False
    return scope


def find_expr(typ) -> list[EXPR]:
    from .exprtype import ExprType
    from .functiontype import FunctionType

    if not isinstance(typ, Type):
        return []
    if typ.is_expr():
        expr_type = cast(ExprType, typ)
        return [expr_type.expr]
    elif typ.is_list():
        return find_expr(typ.length) + find_expr(typ.element)
    elif typ.is_tuple():
        return find_expr(typ.element) + find_expr(typ.length)
    elif typ.is_function():
        func_type = cast(FunctionType, typ)
        exprs: list[EXPR] = []
        for pt in func_type.param_types:
            exprs.extend(find_expr(pt))
        exprs.extend(find_expr(typ.return_type))
        return exprs
    else:
        return []
