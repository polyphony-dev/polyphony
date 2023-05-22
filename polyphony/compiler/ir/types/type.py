from ...common.env import env

class Type(object):
    ANY_LENGTH = -1

    def __init__(self, name, explicit):
        self._name = name
        self._explicit = explicit

    @property
    def name(self):
        return self._name

    @property
    def explicit(self):
        return self._explicit

    def __getattr__(self, name):
        if name.startswith('is_'):
            typename = name[3:]
            return lambda: self.name == typename
        else:
            raise AttributeError(name)

    #def _with_x(self, attrname, value):
    #    copy = Type(self.name, **self.attrs.copy())
    #    copy.attrs[attrname] = value
    #    return copy

    def clone(self, **args):
        raise NotImplementedError()

    @classmethod
    def from_annotation(cls, ann, scope, is_lib=False):
        if isinstance(ann, str):
            t = None
            if ann in env.all_scopes:
                scope = env.all_scopes[ann]
                if scope.is_typeclass():
                    t = Type.from_typeclass(scope, explicit=True)
                else:
                    t = Type.object(scope, explicit=True)
            elif ann == 'int':
                t = Type.int(explicit=True)
            elif ann == 'uint':
                t = Type.int(signed=False, explicit=True)
            elif ann == 'bool':
                t = Type.bool(explicit=True)
            elif ann == 'list':
                t = Type.list(Type.undef(), explicit=True)
            elif ann == 'tuple':
                t = Type.tuple(Type.undef(), Type.ANY_LENGTH, explicit=True)
            elif ann == 'object':
                t = Type.object(None, explicit=True)
            elif ann == 'str':
                t = Type.str(explicit=True)
            elif ann == 'None':
                t = Type.none(explicit=True)
            elif ann == 'generic':
                t = Type.klass(None, explicit=True)
            elif ann == '...':
                t = Type.ellipsis_t
            else:
                while scope:
                    sym = scope.find_sym(ann)
                    if sym:
                        break
                    else:
                        scope = scope.parent
                if sym and sym.typ.has_valid_scope():
                    type_scope = sym.typ.scope
                    if type_scope.is_typeclass():
                        t = Type.from_typeclass(type_scope, explicit=True)
                    else:
                        t = Type.object(type_scope, explicit=True)
                else:
                    raise NameError(ann + ' is not defined')
            return t
        elif isinstance(ann, tuple):
            assert len(ann) == 2
            first = ann[0]
            second = ann[1]
            if isinstance(first, tuple):  # in case of Type[T][Length]
                t = Type.from_annotation(first, scope)
                if t.is_seq():
                    length = int(second)
                    t = t.clone(length=length)
                else:
                    assert False
                return t
            elif isinstance(first, str):  # in case of Type[T]
                sym = scope.find_sym(first)
                if not sym:
                    raise NameError(first + ' is not defined')
                target_scope = sym.typ.scope
                assert target_scope
                if isinstance(second, tuple):
                    elms = [Type.from_annotation(elm, scope) for elm in second]
                    if len(elms) == 2 and elms[1].is_ellipsis():
                        pass
                    elif not all([elms[0] == elm for elm in elms[1:]]):
                        raise TypeError('multiple type tuple is not supported yet')
                elif isinstance(second, str):
                    elms = [Type.from_annotation(second, scope)]
                else:
                    assert False
                if target_scope.is_typeclass():
                    t = Type.from_typeclass(target_scope, elms, explicit=True)
                    if t.is_seq():
                        t = t.clone(length=Type.ANY_LENGTH)
                    return t
        elif ann is None:
            return Type.undef()
        assert False

    @classmethod
    def from_ir(cls, ann, explicit=False):
        from ..ir import IR, IRExp, CONST, TEMP, ATTR, MREF, ARRAY, EXPR
        from ..symbol import Symbol
        assert ann
        assert isinstance(ann, IR)

        if ann.is_a(CONST) and ann.value is None:
            t = Type.none(explicit)
        elif ann.is_a(TEMP) and ann.symbol.typ.has_valid_scope():
            ann_sym_type = ann.symbol.typ
            scope = ann_sym_type.scope
            if scope and scope.is_typeclass():
                t = Type.from_typeclass(scope, explicit=explicit)
            else:
                t = Type.object(scope, explicit)
        elif ann.is_a(ATTR) and isinstance(ann.symbol, Symbol) and ann.symbol.typ.has_valid_scope():
            ann_attr_type = ann.symbol.typ
            scope = ann_attr_type.scope
            if scope.is_typeclass():
                t = Type.from_typeclass(scope, explicit=explicit)
            else:
                t = Type.object(scope, explicit)
        elif ann.is_a(MREF):
            if ann.mem.is_a(MREF):
                t = Type.from_ir(ann.mem, explicit)
                if ann.offset.is_a(CONST):
                    t = t.clone(length=ann.offset.value)
                else:
                    t = t.clone(length=Type.from_ir(ann.offset, explicit))
            else:
                t = Type.from_ir(ann.mem, explicit)
                if t.is_int():
                    assert ann.offset.is_a(CONST)
                    t = t.clone(width=ann.offset.value)
                elif t.is_seq():
                    t = t.clone(element=Type.from_ir(ann.offset, explicit))
                elif t.is_class():
                    elm_t = Type.from_ir(ann.offset, explicit)
                    if elm_t.is_object():
                        t = t.clone(scope=elm_t.scope)
                    else:
                        type_scope = Type.to_scope(elm_t)
                        t = t.clone(scope=type_scope)
        elif ann.is_a(ARRAY):
            assert ann.repeat.is_a(CONST) and ann.repeat.value == 1
            assert ann.is_mutable is False
            # FIXME: tuple should have more than one type
            return Type.from_ir(ann.items[0], explicit)
        else:
            assert ann.is_a(IRExp)
            assert explicit is True
            t = Type.expr(EXPR(ann))
        t = t.clone(explicit=explicit)
        return t

    @classmethod
    def from_typeclass(cls, scope, elms=None, explicit=True):
        assert scope.is_typeclass()
        if scope.base_name == 'int':
            return Type.int(explicit=explicit)
        elif scope.base_name == 'uint':
            return Type.int(signed=False, explicit=explicit)
        elif scope.base_name == 'bool':
            return Type.bool(explicit=explicit)
        elif scope.base_name == 'bit':
            return Type.int(1, signed=False, explicit=explicit)
        elif scope.base_name == 'object':
            return Type.object(None, explicit=explicit)
        elif scope.base_name == 'generic':
            return Type.klass(None, explicit=explicit)
        elif scope.base_name == 'Type':
            raise NotImplementedError()
        elif scope.base_name == 'function':
            return Type.function(None, explicit=explicit)
        elif scope.base_name == 'str':
            return Type.str(explicit=explicit)
        elif scope.base_name == 'list':
            return Type.list(Type.undef(), explicit=explicit)
        elif scope.base_name == 'tuple':
            return Type.tuple(Type.undef(), Type.ANY_LENGTH, explicit=explicit)
        elif scope.base_name.startswith('int'):
            return Type.int(int(scope.base_name[3:]), explicit=explicit)
        elif scope.base_name.startswith('uint'):
            return Type.int(int(scope.base_name[4:]), signed=False, explicit=explicit)
        elif scope.base_name.startswith('bit'):
            return Type.int(int(scope.base_name[3:]), signed=False, explicit=explicit)
        elif scope.base_name == ('Int'):
            return Type.int(explicit=explicit)
        elif scope.base_name == ('List'):
            if elms:
                assert len(elms) == 1
                return Type.list(elms[0], explicit=explicit)
            else:
                return Type.list(Type.undef(), explicit=explicit)
        elif scope.base_name == ('Tuple'):
            if elms:
                if len(elms) == 2 and elms[1].is_ellipsis():
                    length = Type.ANY_LENGTH
                else:
                    length = len(elms)
                # TODO: multiple type tuple
                return Type.tuple(elms[0], length, explicit=explicit)
            else:
                return Type.tuple(Type.undef(), Type.ANY_LENGTH, explicit=explicit)
        else:
            print(scope.name)
            assert False

    @classmethod
    def to_scope(cls, t):
        if t.is_int():
            return t.scope, {}
        elif t.is_bool():
            return t.scope, {}
        elif t.is_str():
            return t.scope, {}
        elif t.is_list():
            scope = env.scopes['__builtin__.list']
        elif t.is_tuple():
            scope = env.scopes['__builtin__.tuple']
        elif t.is_object():
            scope = env.scopes['__builtin__.object']
        else:
            assert False
        return scope


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
            param_ts = []
        from .functiontype import FunctionType
        return FunctionType(scope, ret_t, param_ts, explicit)

    @classmethod
    def object(cls, scope, explicit=False):
        from .objecttype import ObjectType
        return ObjectType(scope, explicit)

    @classmethod
    def klass(cls, scope, explicit=False):
        from .classtype import ClassType
        return ClassType(scope, explicit)

    @classmethod
    def port(cls, portcls, attrs):
        from .porttype import PortType
        return PortType(portcls, attrs)

    @classmethod
    def namespace(cls, scope, explicit=False):
        from .namespacetype import NamespaceType
        return NamespaceType(scope, explicit)

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
                name = t.scope.scope_id
                s = f'c{name}'
            elif t.is_int():
                s = f'i{t.width}'
                s = 'i'
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
