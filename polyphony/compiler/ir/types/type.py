from ...common.env import env

class Type(object):
    ANY_LENGTH = -1

    def __init__(self, name:str, explicit:bool):
        self._name = name
        self._explicit = explicit

    @property
    def name(self) -> str:
        return self._name

    @property
    def explicit(self) -> bool:
        return self._explicit

    def __getattr__(self, name):
        if name.startswith('is_'):
            typename = name[3:]
            return lambda: self.name == typename
        else:
            raise AttributeError(name)

    def clone(self, **args):
        raise NotImplementedError()

    def __str__(self):
        return self._name

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash((self._name, self._explicit))

    def __eq__(self, other):
        return hash(self) == hash(other)

    @classmethod
    def undef(cls):
        from .undefined import UndefinedType
        return UndefinedType()

    @classmethod
    def int(cls, width=None, signed=True, explicit=False):
        from .inttype import IntType
        if width is None:
            width = env.config.default_int_width
        return IntType(width, signed, explicit)

    @classmethod
    def bool(cls, explicit=False):
        from .booltype import BoolType
        return BoolType(explicit)

    @classmethod
    def str(cls, explicit=False):
        from .strtype import StrType
        return StrType(explicit)

    @classmethod
    def none(cls, explicit=False):
        from .nonetype import NoneType
        return NoneType(explicit)

    @classmethod
    def any(cls):
        return Type('any')

    @classmethod
    def list(cls, elm_t, length=ANY_LENGTH, explicit=False):
        from .listtype import ListType
        return ListType(elm_t, length, explicit)

    @classmethod
    def tuple(cls, elm_t, length, explicit=False):
        from .tupletype import TupleType
        return TupleType(elm_t, length, explicit)

    @classmethod
    def function(cls, scope, ret_t=None, param_ts=None, explicit=False):
        if ret_t is None:
            ret_t = Type.undef()
        if param_ts is None:
            param_ts:tuple = tuple()
        from .functiontype import FunctionType
        return FunctionType(scope.name, ret_t, param_ts, explicit)

    @classmethod
    def object(cls, scope, explicit=False):
        from .objecttype import ObjectType
        return ObjectType(scope.name, explicit)

    @classmethod
    def klass(cls, scope, explicit=False):
        from .classtype import ClassType
        return ClassType(scope.name, explicit)

    @classmethod
    def port(cls, portcls, attrs):
        from .porttype import PortType
        return PortType(portcls.name, attrs)

    @classmethod
    def namespace(cls, scope, explicit=False):
        from .namespacetype import NamespaceType
        return NamespaceType(scope.name, explicit)

    @classmethod
    def expr(cls, expr):
        assert expr
        from .exprtype import ExprType
        return ExprType(expr)

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
        return self.name in ('class', 'function', 'object', 'namespace')

    def has_valid_scope(self):
        return self.has_scope() and self.scope

    def is_same(self, other):
        return self.name == other.name

    def can_assign(self, from_t):
        raise NotImplementedError()

    def is_compatible(self, other):
        return self.can_assign(other) and other.can_assign(self)

    def propagate(self, src):
        raise NotImplementedError()

    @classmethod
    def find_expr(cls, typ):
        if not isinstance(typ, Type):
            return []
        if typ.is_expr():
            return [typ.expr]
        elif typ.is_list():
            return cls.find_expr(typ.length) + cls.find_expr(typ.element)
        elif typ.is_tuple():
            return cls.find_expr(typ.element) + cls.find_expr(typ.length)
        elif typ.is_function():
            exprs = []
            for pt in typ.param_types:
                exprs.extend(cls.find_expr(pt))
            exprs.extend(cls.find_expr(typ.return_type))
            return exprs
        else:
            return []

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
