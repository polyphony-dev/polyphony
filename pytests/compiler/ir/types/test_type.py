from polyphony.compiler.common.env import env
from polyphony.compiler.common.common import read_source
from polyphony.compiler.frontend.python.irtranslator import IRTranslator
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import Expr as NewExpr, Const as NewConst, Temp as NewTemp
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.types.typehelper import type_from_ir, type_from_typeclass
from pytests.compiler.base import setup_test
import pytest

from dataclasses import dataclass, field, FrozenInstanceError, asdict, astuple

@dataclass(frozen=True)
class Base:
    name: str
    explicit: bool

@dataclass(frozen=True)
class X(Base):
    xvalue: int

    def __init__(self, xvalue, explicit=True):
        super().__init__('X', explicit)
        object.__setattr__(self, "xvalue", xvalue)

def test_x():
    x = X(100)
    assert x.name == 'X'
    assert x.explicit == True
    assert x.xvalue == 100
    with pytest.raises(FrozenInstanceError) as e:
        x.name = 'Y'

def test_y():
    n = Type.none()
    n2 = n.clone(explicit=True)
    n3 = Type.none(True)
    ns = str(n)
    ns2 = str(n2)
    print(ns, ns2)
    assert n2 == n3

    bool_t1 = Type.bool()
    bool_t2 = bool_t1.clone(explicit=True)

    str_t1 = Type.str(True)
    str_t2 = str_t1.clone(explicit=False)

    int_t1 = Type.int()
    int_t2 = int_t1.clone(explicit=True)


def test_int():
    setup_test()

    i16_t = Type.int(16, signed=False)
    assert i16_t.is_int()
    assert i16_t.width == 16
    assert i16_t.signed == False
    assert i16_t.explicit == False
    assert i16_t.scope.is_typeclass()
    assert i16_t.scope.name == '__builtin__.int'
    assert i16_t == Type.int(16, signed=False)
    assert i16_t != Type.int(16, signed=True)
    assert i16_t != Type.int(8, signed=False)
    assert i16_t != Type.int(16, signed=False, explicit=True)

    u32_t = Type.int(32, signed=False, explicit=True)
    assert u32_t.is_int()
    assert u32_t.width == 32
    assert u32_t.signed == False
    assert u32_t.explicit == True

    assert Type.int(32, True, explicit=True).propagate(Type.int(16, False, explicit=False)) == Type.int(32, True, explicit=True)
    assert Type.int(32, True, explicit=False).propagate(Type.int(16, False, explicit=True)) == Type.int(16, False, explicit=False)
    assert Type.int().propagate(Type.int(64, False, explicit=True)) == Type.int(64, False, explicit=False)
    assert Type.int(32, True, False).propagate(Type.bool(explicit=True)) == Type.int(32, True, explicit=False)

    assert     u32_t.can_assign(Type.int(16, signed=True, explicit=True))
    # bool is not propagate to int, but can be assigned
    assert     u32_t.can_assign(Type.bool())
    assert not u32_t.can_assign(Type.str())
    assert not u32_t.can_assign(Type.none())
    assert not u32_t.can_assign(Type.undef())
    assert not u32_t.can_assign(Type.list(Type.int()))
    assert not u32_t.can_assign(Type.tuple(Type.int(), 100))
    assert not u32_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not u32_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not u32_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not u32_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not u32_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    i8_t = u32_t.clone(width=8, signed=False)
    assert i8_t.width == 8
    assert i8_t.signed == False


def test_bool():
    setup_test()

    bool_t = Type.bool()
    assert bool_t.is_bool()
    assert bool_t.width == 1
    assert bool_t.signed == False
    assert bool_t.explicit == False
    assert bool_t.scope.is_typeclass()
    assert bool_t.scope.name == '__builtin__.bool'
    assert bool_t == Type.bool()
    assert bool_t != Type.bool(explicit=True)

    assert Type.bool(explicit=False).propagate(Type.bool(explicit=True)) == Type.bool(explicit=False)
    assert Type.bool(explicit=False).propagate(Type.int(32, True, explicit=True)) == Type.bool(explicit=False)

    assert bool_t.can_assign(Type.bool())
    assert bool_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not bool_t.can_assign(Type.str())
    assert not bool_t.can_assign(Type.none())
    assert not bool_t.can_assign(Type.undef())
    assert not bool_t.can_assign(Type.list(Type.int()))
    assert not bool_t.can_assign(Type.tuple(Type.int(), 100))
    assert not bool_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not bool_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not bool_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not bool_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not bool_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.bool().clone(explicit=True).explicit == True


def test_str():
    setup_test()

    str_t = Type.str()
    assert str_t.is_str()
    assert str_t.explicit == False
    assert str_t.scope.is_typeclass()
    assert str_t.scope.name == '__builtin__.str'
    assert str_t == Type.str()
    assert str_t != Type.str(explicit=True)

    assert Type.str(explicit=False).propagate(Type.str(explicit=True)) == Type.str(explicit=False)
    assert Type.str(explicit=False).propagate(Type.int(32, True, explicit=True)) == Type.str(explicit=False)

    assert not str_t.can_assign(Type.bool())
    assert not str_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert str_t.can_assign(Type.str())
    assert not str_t.can_assign(Type.none())
    assert not str_t.can_assign(Type.undef())
    assert not str_t.can_assign(Type.list(Type.int()))
    assert not str_t.can_assign(Type.tuple(Type.int(), 100))
    assert not str_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not str_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not str_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not str_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not str_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.str().clone(explicit=True).explicit == True


def test_none():
    setup_test()

    none_t = Type.none()
    assert none_t.is_none()
    assert none_t.explicit == False
    assert none_t.scope.is_typeclass()
    assert none_t.scope.name == '__builtin__.none'
    assert none_t == Type.none()
    assert none_t != Type.none(explicit=True)

    assert Type.none(explicit=False).propagate(Type.none(explicit=True)) == Type.none(explicit=False)
    assert Type.none(explicit=False).propagate(Type.int(32, True, explicit=True)) == Type.none(explicit=False)

    assert not none_t.can_assign(Type.bool())
    assert not none_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not none_t.can_assign(Type.str())
    assert none_t.can_assign(Type.none())
    assert not none_t.can_assign(Type.undef())
    assert not none_t.can_assign(Type.list(Type.int()))
    assert not none_t.can_assign(Type.tuple(Type.int(), 100))
    assert not none_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not none_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not none_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not none_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not none_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.none().clone(explicit=True).explicit == True


def test_undef():
    setup_test()

    undef_t = Type.undef()
    assert undef_t.is_undef()
    assert undef_t.explicit == False
    assert undef_t == Type.undef()

    assert Type.undef().propagate(Type.int(32, True, explicit=False)) == Type.int(32, True, explicit=False)
    assert Type.undef().propagate(Type.bool()) == Type.bool()
    assert Type.undef().propagate(Type.str()) == Type.str()
    assert Type.undef().propagate(Type.none()) == Type.none()
    assert Type.undef().propagate(Type.object(env.scopes['__builtin__.object'])) == Type.object(env.scopes['__builtin__.object'])
    assert Type.undef().propagate(Type.klass(env.scopes['__builtin__.object'])) == Type.klass(env.scopes['__builtin__.object'])
    assert Type.undef().propagate(Type.function(env.scopes['__builtin__.print'])) == Type.function(env.scopes['__builtin__.print'])
    assert Type.undef().propagate(Type.namespace(env.scopes['__builtin__'])) == Type.namespace(env.scopes['__builtin__'])
    assert Type.undef().propagate(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__'])) == Type.expr(EXPR(CONST(1)), env.scopes['__builtin__'])

    assert undef_t.can_assign(Type.bool())
    assert undef_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert undef_t.can_assign(Type.str())
    assert undef_t.can_assign(Type.none())
    assert undef_t.can_assign(Type.undef())
    assert undef_t.can_assign(Type.list(Type.int()))
    assert undef_t.can_assign(Type.tuple(Type.int(), 100))
    assert undef_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert undef_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert undef_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert undef_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert undef_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))


def test_list():
    setup_test()

    list_t = Type.list(Type.undef())
    assert list_t.is_list()
    assert list_t.element.is_undef()
    assert list_t.length == Type.ANY_LENGTH
    assert list_t.is_any_length()
    assert list_t.explicit is False
    assert list_t == Type.list(Type.undef())

    list_t = Type.list(Type.int(), 100, explicit=True)
    assert list_t.element.is_int()
    assert list_t.length == 100
    assert list_t.explicit is True
    assert list_t == Type.list(Type.int(), 100, explicit=True)
    assert list_t != Type.list(Type.int(16), 100, explicit=True)
    assert list_t != Type.list(Type.int(), 101, explicit=True)
    assert list_t != Type.list(Type.int(), 100, explicit=False)

    assert Type.list(Type.int()).propagate(Type.int(32, True, explicit=True)) == Type.list(Type.int())
    assert Type.list(Type.int()).propagate(Type.list(Type.int(), 100, explicit=True)) == Type.list(Type.int(), 100, explicit=False)
    assert Type.list(Type.int()).propagate(Type.list(Type.int(), 100, explicit=False)) == Type.list(Type.int(), 100, explicit=False)
    assert Type.list(Type.bool()).propagate(Type.list(Type.int(), 100, explicit=True)) == Type.list(Type.bool(), 100)
    assert Type.list(Type.bool()).propagate(Type.tuple(Type.int(), 100, explicit=True)) == Type.list(Type.bool(), explicit=False)

    assert not list_t.can_assign(Type.bool())
    assert not list_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not list_t.can_assign(Type.str())
    assert not list_t.can_assign(Type.none())
    assert not list_t.can_assign(Type.undef())
    assert     list_t.can_assign(Type.list(Type.int()))
    assert     list_t.can_assign(Type.list(Type.int(), 100))
    assert     list_t.can_assign(Type.list(Type.int(16), 100))
    assert     list_t.can_assign(Type.list(Type.int(64), 100))
    assert     list_t.can_assign(Type.list(Type.bool(), 100))
    assert not list_t.can_assign(Type.list(Type.str()))
    assert not list_t.can_assign(Type.list(Type.int(), 101))
    assert not list_t.can_assign(Type.list(Type.int(), 99))
    assert     list_t.can_assign(Type.list(Type.int(), Type.expr(EXPR(CONST(99)), env.scopes['__builtin__'])))
    assert     Type.list(Type.int(), Type.expr(EXPR(CONST(99)), env.scopes['__builtin__'])).can_assign(Type.list(Type.int(), 10))
    assert not list_t.can_assign(Type.tuple(Type.int(), 100))
    assert not Type.list(Type.int(), 100).can_assign(Type.tuple(Type.int(), 100))
    assert not list_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not list_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not list_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not list_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not list_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.list(Type.int()).clone(explicit=True).explicit == True
    assert Type.list(Type.int()).clone(element=Type.bool()).element == Type.bool()
    assert Type.list(Type.int()).clone(length=1).length == 1
    assert Type.list(Type.int()).clone(ro=True).ro == True


def test_tuple():
    setup_test()

    tuple_t = Type.tuple(Type.undef(), 3)
    assert tuple_t.is_tuple()
    assert tuple_t.element.is_undef()
    assert tuple_t.length == 3
    assert tuple_t.explicit is False
    assert tuple_t.scope.name == '__builtin__.tuple'
    assert tuple_t == Type.tuple(Type.undef(), 3)
    assert tuple_t != Type.tuple(Type.undef(), 4)

    tuple_t = Type.tuple(Type.int(), 100, explicit=True)
    assert tuple_t.element.is_int()
    assert tuple_t.length == 100
    assert tuple_t.explicit is True
    assert tuple_t == Type.tuple(Type.int(), 100, explicit=True)
    assert tuple_t != Type.tuple(Type.int(16), 100, explicit=True)
    assert tuple_t != Type.tuple(Type.int(), 101, explicit=True)
    assert tuple_t != Type.tuple(Type.int(), 100, explicit=False)

    assert Type.tuple(Type.int(), 3).propagate(Type.tuple(Type.int(), 10, explicit=True)) == Type.tuple(Type.int(), 3)
    assert Type.tuple(Type.int(), 3).propagate(Type.tuple(Type.int(), 3, explicit=True)) == Type.tuple(Type.int(), 3)
    # element type is propagated if lengths are equal
    assert Type.tuple(Type.int(), 3).propagate(Type.tuple(Type.int(64, False, explicit=True), 3)) == Type.tuple(Type.int(64, False), 3)
    # element type is not propagated if lengths are different
    assert Type.tuple(Type.int(), 3).propagate(Type.tuple(Type.int(64, False, explicit=True), 10)) == Type.tuple(Type.int(), 3)
    assert Type.tuple(Type.bool(), 3).propagate(Type.tuple(Type.int(), 100, explicit=True)) == Type.tuple(Type.bool(), 3)
    assert Type.tuple(Type.bool(), 3).propagate(Type.tuple(Type.int(), 100, explicit=True)) == Type.tuple(Type.bool(), 3)
    assert Type.tuple(Type.bool(), Type.ANY_LENGTH).propagate(Type.tuple(Type.bool(), 100, explicit=True)) == Type.tuple(Type.bool(), 100)
    assert Type.tuple(Type.bool(), Type.ANY_LENGTH).propagate(Type.tuple(Type.str(), 100, explicit=True)) == Type.tuple(Type.bool(), Type.ANY_LENGTH)

    assert not tuple_t.can_assign(Type.bool())
    assert not tuple_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not tuple_t.can_assign(Type.str())
    assert not tuple_t.can_assign(Type.none())
    assert not tuple_t.can_assign(Type.undef())
    assert not tuple_t.can_assign(Type.list(Type.int()))
    assert not tuple_t.can_assign(Type.list(Type.int(), 100))
    assert     tuple_t.can_assign(Type.tuple(Type.int(), 100))
    assert     tuple_t.can_assign(Type.tuple(Type.int(16), 100))
    assert     tuple_t.can_assign(Type.tuple(Type.int(64), 100))
    assert     tuple_t.can_assign(Type.tuple(Type.bool(), 100))
    assert not tuple_t.can_assign(Type.tuple(Type.str(), 100))
    assert not tuple_t.can_assign(Type.tuple(Type.int(), 101))
    assert not tuple_t.can_assign(Type.tuple(Type.int(), 99))
    assert not tuple_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not tuple_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not tuple_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not tuple_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not tuple_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.tuple(Type.int(), 3).clone(explicit=True).explicit == True
    assert Type.tuple(Type.int(), 3).clone(element=Type.bool()).element == Type.bool()
    assert Type.tuple(Type.int(), 3).clone(length=1).length == 1


def new_scope(parent, name, tags):
    scope = Scope.create(parent, name, tags)
    if parent:
        if 'class' in tags or 'typeclass' in tags:
            parent.add_sym(name, set(), typ=Type.klass(scope, True))
        elif 'function' in tags:
            parent.add_sym(name, set(), typ=Type.function(scope, True))
        else:
            assert False
    blk = Block(scope)
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)
    return scope


def test_user_object():
    setup_test()

    top = new_scope(None, 'top', {'namespace'})
    C = new_scope(top, 'C', {'class'})
    D = new_scope(top, 'D', {'class'})
    C_instance = C.instantiate('1')

    cls_obj = env.scopes['__builtin__.object']
    obj_t = Type.object(cls_obj)
    C_t = Type.object(C)
    assert C_t.is_object()
    assert C_t.scope.name == 'top.C'
    assert C_t.explicit is False
    assert C_t == Type.object(C)
    assert obj_t != C_t
    assert C_t != Type.object(D)

    assert Type.object(C, explicit=False).propagate(Type.object(C, explicit=True)) == Type.object(C, explicit=False)
    assert Type.object(C, explicit=False).propagate(Type.object(C, explicit=False)) == Type.object(C, explicit=False)
    assert Type.object(C).propagate(Type.object(D, explicit=True)) == Type.object(C, explicit=False)
    assert Type.object(C).propagate(Type.object(D, explicit=False)) == Type.object(C, explicit=False)
    assert Type.object(C).propagate(Type.object(C_instance)) == Type.object(C_instance)

    assert not Type.object(C).can_assign(Type.bool())
    assert not Type.object(C).can_assign(Type.int(16, signed=True, explicit=True))
    assert not Type.object(C).can_assign(Type.str())
    assert not Type.object(C).can_assign(Type.none())
    assert not Type.object(C).can_assign(Type.undef())
    assert not Type.object(C).can_assign(Type.list(Type.int()))
    assert not Type.object(C).can_assign(Type.list(Type.int(), 100))
    assert not Type.object(C).can_assign(Type.tuple(Type.int(), 100))
    assert not Type.object(C).can_assign(Type.object(cls_obj))
    assert     Type.object(C).can_assign(Type.object(C))
    assert not Type.object(C).can_assign(Type.object(D))
    assert     Type.object(C).can_assign(Type.object(C_instance))
    assert not Type.object(C_instance).can_assign(C_t)

    assert not Type.object(C).can_assign(Type.klass(C))
    assert not Type.object(C).can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not Type.object(C).can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not Type.object(C).can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    clonec = Type.object(C).clone(scope=C_instance)
    assert clonec.scope is C_instance


def test_generic_object():
    setup_test()

    top = new_scope(None, 'top', {'namespace'})
    C = new_scope(top, 'C', {'class'})
    D = new_scope(top, 'D', {'class'})
    C_instance = C.instantiate('1')

    Object = env.scopes['__builtin__.object']
    obj_t = Type.object(Object)
    C_t = Type.object(C)
    assert obj_t.is_object()
    assert obj_t.scope.is_typeclass()
    assert obj_t.scope.is_object()
    assert obj_t.explicit is False
    assert obj_t == Type.object(Object)
    assert obj_t != C_t


    # generic object can propagate to any object but undef
    assert Type.object(Object).propagate(Type.int()) == Type.int()
    assert Type.object(Object).propagate(Type.bool()) == Type.bool()
    assert Type.object(Object).propagate(Type.str()) == Type.str()
    assert Type.object(Object).propagate(Type.none()) == Type.none()
    assert Type.object(Object).propagate(Type.list(Type.int())) == Type.list(Type.int())
    assert Type.object(Object).propagate(Type.list(Type.int(), 100)) == Type.list(Type.int(), 100)
    assert Type.object(Object).propagate(Type.tuple(Type.int(), 100)) == Type.tuple(Type.int(), 100)
    assert Type.object(Object).propagate(Type.object(C)) == Type.object(C)

    # cases that do not propagate
    assert Type.object(Object).propagate(Type.undef()) == Type.object(Object)
    assert Type.object(Object).propagate(Type.klass(Object)) == Type.object(Object)
    assert Type.object(Object).propagate(Type.function(Object)) == Type.object(Object)
    assert Type.object(Object).propagate(Type.namespace(env.scopes['__builtin__'])) == Type.object(Object)
    assert Type.object(Object).propagate(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__'])) == Type.object(Object)

    # explicit property is never propagated
    assert Type.object(Object, explicit=False).propagate(Type.object(Object, explicit=True)) == Type.object(Object, explicit=False)
    assert Type.object(Object, explicit=False).propagate(Type.object(Object, explicit=False)) == Type.object(Object, explicit=False)
    assert Type.object(Object, explicit=True).propagate(Type.object(Object, explicit=True)) == Type.object(Object, explicit=True)
    assert Type.object(Object, explicit=True).propagate(Type.object(Object, explicit=False)) == Type.object(Object, explicit=True)

    # can assign
    assert     Type.object(Object).can_assign(Type.bool())
    assert     Type.object(Object).can_assign(Type.int(16, signed=True, explicit=True))
    assert     Type.object(Object).can_assign(Type.str())
    assert     Type.object(Object).can_assign(Type.none())
    assert not Type.object(Object).can_assign(Type.undef())
    assert     Type.object(Object).can_assign(Type.list(Type.int()))
    assert     Type.object(Object).can_assign(Type.list(Type.int(), 100))
    assert     Type.object(Object).can_assign(Type.tuple(Type.int(), 100))
    assert     Type.object(Object).can_assign(Type.object(C))
    # can not assign
    assert not Type.object(Object).can_assign(Type.klass(Object))
    assert not Type.object(Object).can_assign(Type.function(env.scopes['__builtin__.print']))
    assert not Type.object(Object).can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not Type.object(Object).can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))


def test_class():
    setup_test()

    top = new_scope(None, 'top', {'namespace'})
    C = new_scope(top, 'C', {'class'})
    D = new_scope(top, 'D', {'class'})
    C_instance = C.instantiate('1')

    cls = env.scopes['__builtin__.object']
    cls_t = Type.klass(cls)
    assert cls_t.is_class()
    assert cls_t.scope.is_typeclass()
    assert cls_t.explicit is False
    assert cls_t == Type.klass(cls)
    assert cls_t != Type.klass(C)
    assert Type.klass(C) == Type.klass(C)
    assert Type.klass(C) != Type.klass(D)

    assert Type.klass(cls).propagate(Type.klass(C, explicit=True)) == Type.klass(C, explicit=False)
    assert Type.klass(cls).propagate(Type.klass(C, explicit=False)) == Type.klass(C, explicit=False)
    assert Type.klass(C).propagate(Type.klass(cls, explicit=True)) == Type.klass(C, explicit=False)
    assert Type.klass(C).propagate(Type.klass(cls, explicit=False)) == Type.klass(C, explicit=False)

    assert not cls_t.can_assign(Type.bool())
    assert not cls_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not cls_t.can_assign(Type.str())
    assert not cls_t.can_assign(Type.none())
    assert not cls_t.can_assign(Type.undef())
    assert not cls_t.can_assign(Type.list(Type.int()))
    assert not cls_t.can_assign(Type.list(Type.int(), 100))
    assert not cls_t.can_assign(Type.tuple(Type.int(), 100))
    assert not cls_t.can_assign(Type.object(cls))
    assert not cls_t.can_assign(Type.object(C))
    assert not cls_t.can_assign(Type.function(env.scopes['__builtin__.print']))
    assert     cls_t.can_assign(Type.klass(cls))
    assert     cls_t.can_assign(Type.klass(C))
    assert not Type.klass(C).can_assign(Type.klass(cls))
    assert     Type.klass(C).can_assign(Type.klass(C))
    assert not cls_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not cls_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.klass(C).clone(scope=C_instance).scope is C_instance


def test_function():
    setup_test()

    top = new_scope(None, 'top', {'namespace'})
    F = new_scope(top, 'f', {'function'})
    G = new_scope(top, 'g', {'function'})

    cls = env.scopes['__builtin__.object']
    func_t = Type.function(cls)
    assert func_t.is_function()
    assert func_t.scope.is_typeclass()
    assert func_t.explicit is False
    assert func_t == Type.function(cls)
    assert func_t != Type.function(F)
    func_t = Type.function(F, ret_t=Type.none(), param_ts=(Type.int(),), explicit=True)
    assert func_t.return_type.is_none()
    assert func_t.param_types[0].is_int()

    assert Type.function(F) == Type.function(F)
    assert Type.function(F, ret_t=Type.int()) == Type.function(F, ret_t=Type.int())
    assert Type.function(F, ret_t=Type.int()) != Type.function(F, ret_t=Type.none())
    assert Type.function(F, ret_t=Type.none(), param_ts=[Type.int()]) == Type.function(F, ret_t=Type.none(), param_ts=[Type.int()])
    assert Type.function(F, ret_t=Type.none(), param_ts=[Type.int()]) != Type.function(F, ret_t=Type.none(), param_ts=[Type.bool()])
    assert Type.function(F) != Type.function(G)

    assert Type.function(cls).propagate(Type.function(F, explicit=True)) == Type.function(F, explicit=False)
    assert Type.function(cls).propagate(Type.function(F, ret_t=Type.none(), explicit=True)) == Type.function(F, ret_t=Type.none(), explicit=False)
    assert Type.function(cls).propagate(Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=True)) == Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=False)
    assert Type.function(cls).propagate(Type.function(F, explicit=False)) == Type.function(F, explicit=False)
    assert Type.function(cls).propagate(Type.function(F, ret_t=Type.none(), explicit=False)) == Type.function(F, ret_t=Type.none(), explicit=False)
    assert Type.function(cls).propagate(Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=False)) == Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=False)
    assert Type.function(F).propagate(Type.function(cls, explicit=True)) == Type.function(F, explicit=False)
    assert Type.function(F).propagate(Type.function(G, explicit=True)) == Type.function(F, explicit=False)
    assert Type.function(F).propagate(Type.function(cls, explicit=False)) == Type.function(F, explicit=False)
    assert Type.function(F).propagate(Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=False)) == Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=False)
    assert Type.function(F).propagate(Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=True)) == Type.function(F, ret_t=Type.none(), param_ts=[Type.int()], explicit=False)

    func_t = Type.function(cls)
    assert not func_t.can_assign(Type.bool())
    assert not func_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not func_t.can_assign(Type.str())
    assert not func_t.can_assign(Type.none())
    assert not func_t.can_assign(Type.undef())
    assert not func_t.can_assign(Type.list(Type.int()))
    assert not func_t.can_assign(Type.list(Type.int(), 100))
    assert not func_t.can_assign(Type.tuple(Type.int(), 100))
    assert not func_t.can_assign(Type.object(cls))
    assert     func_t.can_assign(Type.function(cls))
    assert     func_t.can_assign(Type.function(F))
    assert not func_t.can_assign(Type.klass(cls))
    assert not func_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not func_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.function(F).clone(scope=G).scope is G


def test_namespace():
    setup_test()

    top = new_scope(None, 'top', {'namespace'})
    other = new_scope(None, 'lib', {'namespace'})

    cls = env.scopes['__builtin__']
    ns_t = Type.namespace(top)
    assert ns_t.is_namespace()
    assert ns_t.scope is top
    assert ns_t.explicit is False
    assert ns_t == Type.namespace(top)
    assert ns_t != Type.namespace(cls)

    assert Type.namespace(cls).propagate(Type.namespace(top, explicit=True)) == Type.namespace(cls)
    assert Type.namespace(cls).propagate(Type.namespace(top, explicit=False)) == Type.namespace(cls)
    assert Type.namespace(top).propagate(Type.namespace(cls, explicit=True)) == Type.namespace(top, explicit=False)
    assert Type.namespace(top).propagate(Type.namespace(cls, explicit=False)) == Type.namespace(top, explicit=False)

    assert not ns_t.can_assign(Type.bool())
    assert not ns_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not ns_t.can_assign(Type.str())
    assert not ns_t.can_assign(Type.none())
    assert not ns_t.can_assign(Type.undef())
    assert not ns_t.can_assign(Type.list(Type.int()))
    assert not ns_t.can_assign(Type.list(Type.int(), 100))
    assert not ns_t.can_assign(Type.tuple(Type.int(), 100))
    assert not ns_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not ns_t.can_assign(Type.function(env.scopes['__builtin__.object']))
    assert not ns_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not ns_t.can_assign(Type.namespace(cls))
    assert not ns_t.can_assign(Type.namespace(top))
    assert not ns_t.can_assign(Type.expr(EXPR(CONST(1)), env.scopes['__builtin__']))

    assert Type.namespace(cls).clone(scope=top).scope is top


def test_expr():
    setup_test()

    top = new_scope(None, 'top', {'namespace'})
    Int = new_scope(top, 'Int', {'typeclass'})

    expr_t = Type.expr(EXPR(TEMP('Int')), top)
    assert expr_t.is_expr()
    assert expr_t.explicit is True
    assert expr_t == Type.expr(EXPR(TEMP('Int')), top)
    assert expr_t != Type.expr(EXPR(CONST(0)), top)

    assert Type.expr(EXPR(CONST(0)), top).propagate(Type.expr(EXPR(TEMP('Int')), top)) == Type.expr(EXPR(TEMP('Int')), top)
    assert Type.expr(EXPR(TEMP('Int')), top).propagate(Type.expr(EXPR(CONST(0)), top)) == Type.expr(EXPR(CONST(0)), top)

    assert not expr_t.can_assign(Type.bool())
    assert not expr_t.can_assign(Type.int(16, signed=True, explicit=True))
    assert not expr_t.can_assign(Type.str())
    assert not expr_t.can_assign(Type.none())
    assert not expr_t.can_assign(Type.undef())
    assert not expr_t.can_assign(Type.list(Type.int()))
    assert not expr_t.can_assign(Type.list(Type.int(), 100))
    assert not expr_t.can_assign(Type.tuple(Type.int(), 100))
    assert not expr_t.can_assign(Type.object(env.scopes['__builtin__.object']))
    assert not expr_t.can_assign(Type.function(env.scopes['__builtin__.object']))
    assert not expr_t.can_assign(Type.klass(env.scopes['__builtin__.object']))
    assert not expr_t.can_assign(Type.namespace(env.scopes['__builtin__']))
    assert not expr_t.can_assign(Type.namespace(top))
    assert expr_t.can_assign(Type.expr(EXPR(TEMP('Int')), top))
    assert expr_t.can_assign(Type.expr(EXPR(CONST(0)), top))

    assert Type.expr(EXPR(CONST(0)), top).clone(expr=EXPR(TEMP('Int'))).expr == EXPR(TEMP('Int'))

def test_list_length_expr():
    setup_test()

    top = new_scope(None, 'top', {'namespace'})
    elm_t = Type.int()
    length = Type.expr(EXPR(TEMP('x')), top)
    list_t = Type.list(elm_t, length)
    slist = str(list_t)
    print(slist)

def test_port():
    setup_test()
    top = new_scope(None, 'top', {'namespace'})
    PortClass = new_scope(top, 'Port', {'class', 'port'})
    #  dtype
    #  direction ... in | out
    #  init      ... initial value
    #  assigned    ... True | False
    #  root_symbol ... symbol
    attrs = {
        "dtype": Type.int(),
        "direction": "in",
        "init": 0,
        "assigned": False,
        "root_symbol": None,
    }
    port_t = Type.port(PortClass, attrs)
    assert port_t.is_port()
    assert port_t.dtype == Type.int()
    assert port_t.direction == "in"
    assert port_t.init == 0
    assert port_t.assigned is False
    assert port_t.root_symbol is None
    attrs = {
        "dtype": Type.int(),
        "direction": "out",
        "init": 0,
        "assigned": False,
        "root_symbol": None,
    }
    port_t2 = Type.port(PortClass, attrs)
    assert port_t != port_t2

def test_common_function():
    setup_test()

    assert Type.int().is_scalar()
    assert Type.bool().is_scalar()
    assert Type.str().is_scalar()
    assert not Type.none().is_scalar()
    assert not Type.undef().is_scalar()
    assert not Type.list(Type.int()).is_scalar()
    assert not Type.tuple(Type.int(), 1).is_scalar()
    cls = env.scopes['__builtin__.object']
    ns = env.scopes['__builtin__']
    assert not Type.object(cls).is_scalar()
    assert not Type.function(cls).is_scalar()
    assert not Type.klass(cls).is_scalar()
    assert not Type.namespace(ns).is_scalar()
    assert not Type.expr(EXPR(CONST(0)), env.scopes['__builtin__']).is_scalar()

    assert not Type.int().is_seq()
    assert not Type.bool().is_seq()
    assert not Type.str().is_seq()
    assert not Type.none().is_seq()
    assert not Type.undef().is_seq()
    assert Type.list(Type.int()).is_seq()
    assert Type.tuple(Type.int(), 1).is_seq()
    assert not Type.object(cls).is_seq()
    assert not Type.function(cls).is_seq()
    assert not Type.klass(cls).is_seq()
    assert not Type.namespace(ns).is_seq()
    assert not Type.expr(EXPR(CONST(0)), env.scopes['__builtin__']).is_seq()

    assert not Type.int().is_containable()
    assert not Type.bool().is_containable()
    assert not Type.str().is_containable()
    assert not Type.none().is_containable()
    assert not Type.undef().is_containable()
    assert not Type.list(Type.int()).is_containable()
    assert not Type.tuple(Type.int(), 1).is_containable()
    assert not Type.object(cls).is_containable()
    assert not Type.function(cls).is_containable()
    assert Type.klass(cls).is_containable()
    assert Type.namespace(ns).is_containable()
    assert not Type.expr(EXPR(CONST(0)), env.scopes['__builtin__']).is_containable()


def test_type_from_ir():
    setup_test()
    top = env.scopes['@top']   # new_scope(None, 'top', {'global'})
    int_class = env.scopes['__builtin__.int']  # new_scope(top, 'int', {'typeclass'})
    list_class = env.scopes['__builtin__.list']  # new_scope(top, 'list', {'typeclass'})
    str_class = env.scopes['__builtin__.str']  # new_scope(top, 'str', {'typeclass'})
    usr_class = new_scope(top, 'UserClass',  {'class'})
    usr_sub_class = new_scope(usr_class, 'SubClass',  {'class'})
    usr_class.add_sym('Sub', set(), typ=Type.klass(usr_sub_class))

    t = type_from_ir(top, CONST(None), explicit=True)
    assert t.is_none()

    t = type_from_ir(top, CONST(123), explicit=True)
    assert t.is_expr()
    assert isinstance(t.expr, NewExpr)
    assert isinstance(t.expr.exp, NewConst)
    assert t.expr.exp.value == 123


    # x: int
    int_calss_ir = TEMP('int')
    t = type_from_ir(top, int_calss_ir, explicit=True)
    assert t.is_int()
    assert t.explicit

    # x: UserClass
    usr_calss_ir = TEMP('UserClass')
    t = type_from_ir(top, usr_calss_ir, explicit=True)
    assert t.is_object()
    assert t.scope is usr_class
    assert t.explicit

    # x: str
    str_calss_ir = TEMP('str')
    t = type_from_ir(top, str_calss_ir, explicit=True)
    assert t.is_str()
    assert t.explicit

    # x: UserClass.Sub
    usr_calss_ir = ATTR(TEMP('UserClass'), 'Sub')
    t = type_from_ir(top, usr_calss_ir, explicit=True)
    assert t.is_object()
    assert t.scope is usr_sub_class
    assert t.explicit

    # x: list[int]
    list_class_ir = MREF(TEMP('list'), TEMP('int'))
    t = type_from_ir(top, list_class_ir, explicit=True)
    assert t.is_list()
    assert t.explicit
    assert t.element.is_int()
    assert t.element.explicit
    assert t.length == Type.ANY_LENGTH

    # x: list[int][10]
    list_ir = MREF(
        MREF(
            TEMP('list'),
            TEMP('int')
        ),
        CONST(10)
    )
    t1 = type_from_ir(top, list_ir, explicit=True)
    assert t1.is_list()
    assert t1.length == 10
    assert t1.explicit
    t2 = t1.element
    assert t2.is_int()
    assert t2.explicit
    assert t2.width == 32
    assert t2.signed == True

    # x: list[int][SIZE]
    top.add_sym('SIZE', set(), typ=Type.int())
    list_ir = MREF(
        MREF(
            TEMP('list'),
            TEMP('int')
        ),
        TEMP('SIZE')
    )
    t1 = type_from_ir(top, list_ir, explicit=True)
    assert t1.is_list()
    assert t1.explicit
    length = t1.length
    assert length.is_expr()
    assert isinstance(length.expr, NewExpr)
    assert isinstance(length.expr.exp, NewTemp)

    t2 = t1.element
    assert t2.is_int()
    assert t2.explicit
    assert t2.width == 32
    assert t2.signed == True

    # T: type
    type_sym = top.find_sym('type')
    t = type_from_ir(top, TEMP('type'), explicit=True)
    assert t.is_class()
    assert t.scope.is_object()

    # x: T
    top.add_sym('T', set(), typ=Type.klass('__builtin__.object'))
    t = type_from_ir(top, TEMP('T'), explicit=True)
    assert t.is_expr()
    assert isinstance(t.expr, NewExpr)
    assert isinstance(t.expr.exp, NewTemp)
    assert t.expr.exp.name == 'T'


    # x: bit[usr_class.value]
    # TODO ...

import os

def test_type_from_typeclass():
    setup_test()
    src = 'import polyphony.typing'
    translator = IRTranslator()
    translator.translate(src, '')

    # internal_dir = f'{env.root_dir}{os.path.sep}_internal'
    # typing_package_file = f'{internal_dir}{os.sep}_typing.py'
    # env.set_current_filename(typing_package_file)
    # translator.translate(read_source(typing_package_file), '')

    intcls = env.scopes['__builtin__.int']
    t = type_from_typeclass(intcls)
    assert t.is_int()
    assert t.width == 32
    assert t.signed == True

    boolcls = env.scopes['__builtin__.bool']
    t = type_from_typeclass(boolcls)
    assert t.is_bool()
    assert t.width == 1
    assert t.signed == False

    strcls = env.scopes['__builtin__.str']
    t = type_from_typeclass(strcls)
    assert t.is_str()

    objcls = env.scopes['__builtin__.object']
    t = type_from_typeclass(objcls)
    assert t.is_object()

    funccls = env.scopes['__builtin__.function']
    t = type_from_typeclass(funccls)
    assert t.is_function()

    listcls = env.scopes['__builtin__.list']
    t = type_from_typeclass(listcls)
    assert t.is_list()

    tuplecls = env.scopes['__builtin__.tuple']
    t = type_from_typeclass(tuplecls)
    assert t.is_tuple()

    int64cls = env.scopes['polyphony.typing.int64']
    t = type_from_typeclass(int64cls)
    assert t.is_int()
    assert t.width == 64
    assert t.signed == True

    uint32cls = env.scopes['polyphony.typing.uint32']
    t = type_from_typeclass(uint32cls)
    assert t.is_int()
    assert t.width == 32
    assert t.signed == False

    bitcls = env.scopes['polyphony.typing.bit']
    t = type_from_typeclass(bitcls)
    assert t.is_int()
    assert t.width == 1
    assert t.signed == False

    bit8cls = env.scopes['polyphony.typing.bit8']
    t = type_from_typeclass(bit8cls)
    assert t.is_int()
    assert t.width == 8
    assert t.signed == False

