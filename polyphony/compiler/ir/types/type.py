from __future__ import annotations
from typing import ClassVar, TYPE_CHECKING
from dataclasses import dataclass
from ...common.env import env
if TYPE_CHECKING:
    from ..scope import Scope
    from .booltype import BoolType
    from .classtype import ClassType
    from .exprtype import ExprType
    from .functiontype import FunctionType
    from .inttype import IntType
    from .listtype import ListType
    from .namespacetype import NamespaceType
    from .nonetype import NoneType
    from .objecttype import ObjectType
    from .porttype import PortType
    from .strtype import StrType
    from .tupletype import TupleType
    from .undefined import UndefinedType


@dataclass(frozen=True)
class Type:
    ANY_LENGTH: ClassVar[int] = -1
    name: str
    explicit: bool

    def __getattr__(self, name):
        if name.startswith('is_'):
            typename = name[3:]
            return lambda: self.name == typename
        else:
            raise AttributeError(name)

    def clone(self, **args):
        raise NotImplementedError()

    def __str__(self):
        return self.name

    @classmethod
    def undef(cls) -> UndefinedType:
        from .undefined import UndefinedType
        return UndefinedType()

    @classmethod
    def int(cls, width=None, signed=True, explicit=False) -> IntType:
        from .inttype import IntType
        if width is None:
            width = env.config.default_int_width
        return IntType(explicit, width, signed)

    @classmethod
    def bool(cls, explicit=False) -> BoolType:
        from .booltype import BoolType
        return BoolType(explicit)

    @classmethod
    def str(cls, explicit=False) -> StrType:
        from .strtype import StrType
        return StrType(explicit)

    @classmethod
    def none(cls, explicit=False) -> NoneType:
        from .nonetype import NoneType
        return NoneType(explicit)

    @classmethod
    def any(cls):
        return Type('any')

    @classmethod
    def list(cls, elm_t, length=ANY_LENGTH, explicit=False) -> ListType:
        from .listtype import ListType
        return ListType(explicit, elm_t, length, False)

    @classmethod
    def tuple(cls, elm_t, length, explicit=False) -> TupleType:
        from .tupletype import TupleType
        return TupleType(explicit, elm_t, length)

    @classmethod
    def function(cls, scope, ret_t=None, param_ts=None, explicit=False) -> FunctionType:
        from ..scope import Scope
        if ret_t is None:
            ret_t = Type.undef()
        if param_ts is None:
            param_ts = []
        from .functiontype import FunctionType
        if isinstance(scope, Scope):
            return FunctionType(explicit, scope.name, ret_t, param_ts)
        else:
            return FunctionType(explicit, scope, ret_t, param_ts)

    @classmethod
    def object(cls, scope, explicit=False) -> ObjectType:
        from ..scope import Scope
        from .objecttype import ObjectType
        if isinstance(scope, Scope):
            return ObjectType(explicit, scope.name)
        else:
            return ObjectType(explicit, scope)

    @classmethod
    def klass(cls, scope, explicit=False) -> ClassType:
        from ..scope import Scope
        from .classtype import ClassType
        if isinstance(scope, Scope):
            return ClassType(explicit, scope.name)
        else:
            return ClassType(explicit, scope)
    
    @classmethod
    def port(cls, portcls, attrs) -> PortType:
        from ..scope import Scope
        from .porttype import PortType
        if isinstance(portcls, Scope):
            return PortType(False, portcls.name, attrs)
        else:
            return PortType(False, portcls, attrs)
    
    @classmethod
    def namespace(cls, scope, explicit=False) -> NamespaceType:
        from ..scope import Scope
        from .namespacetype import NamespaceType
        if isinstance(scope, Scope):
            return NamespaceType(explicit, scope.name)
        else:
            return NamespaceType(explicit, scope)

    @classmethod
    def expr(cls, expr) -> ExprType:
        assert expr
        from .exprtype import ExprType
        return ExprType(True, expr)

    @classmethod
    def union(cls, types):
        raise NotImplementedError()

    def is_seq(self):
        return self.name in ('list', 'tuple')

    def is_scalar(self):
        return self.name in ('int', 'bool', 'str')

    def is_containable(self):
        return self.name in ('namespace', 'class')

    def has_scope(self):
        from .scopetype import ScopeType
        return isinstance(self, ScopeType)

    def is_same(self, other):
        return self.name == other.name

    def can_assign(self, from_t):
        raise NotImplementedError()

    def is_compatible(self, other):
        return self.can_assign(other) and other.can_assign(self)

    def propagate(self, src):
        raise NotImplementedError()

    @classmethod
    def mangled_names(cls, types):
        ts = []
        for t in types:
            if t.is_list():
                elm = cls.mangled_names([t.element])
                if t.length != Type.ANY_LENGTH:
                    s = f'l_{elm}_{t.length}'
                else:
                    s = f'l_{elm}'
            elif t.is_tuple():
                elm = cls.mangled_names([t.element])
                if t.length != Type.ANY_LENGTH:
                    elms = ''.join([elm] * t.length)
                else:
                    elms = elm
                s = f't_{elms}'
            elif t.is_class():
                if t.scope.is_typeclass():
                    name = t.scope.base_name
                else:
                    name = t.scope.scope_id
                s = f'c{name}'
            elif t.is_int():
                s = f'i{t.width}'
            elif t.is_bool():
                s = f'b'
            elif t.is_str():
                s = f's'
            elif t.is_object():
                name = t.scope.scope_id
                s = f'o{name}'
            else:
                s = str(t)
            ts.append(s)
        return ''.join(ts)
