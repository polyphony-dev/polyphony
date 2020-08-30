from ..common.env import env


class Type(object):
    ANY_LENGTH = -1

    def __init__(self, name, **attrs):
        self.name = name
        self.attrs = attrs

    def __getattr__(self, name):
        if name.startswith('is_'):
            typename = name[3:]
            return lambda: self.name == typename
        elif name.startswith('get_'):
            attrname = name[4:]
            if attrname not in self.attrs:
                raise AttributeError(name)
            return lambda: self.attrs[attrname]
        elif name.startswith('with_'):
            attrname = name[5:]
            return lambda v: self._with_x(attrname, v)
        elif name.startswith('has_'):
            attrname = name[4:]
            return lambda: attrname in self.attrs
        else:
            raise AttributeError(name)

    def _with_x(self, attrname, value):
        copy = Type(self.name, **self.attrs.copy())
        copy.attrs[attrname] = value
        return copy

    @classmethod
    def from_annotation(cls, ann, scope, is_lib=False):
        if isinstance(ann, str):
            t = None
            if ann in env.all_scopes:
                scope = env.all_scopes[ann]
                if scope.is_typeclass():
                    t = Type.from_typeclass(scope)
                else:
                    t = Type.object(scope)
            elif ann == 'int':
                t = Type.int()
            elif ann == 'uint':
                t = Type.int(signed=False)
            elif ann == 'bool':
                t = Type.bool()
            elif ann == 'list':
                t = Type.list(Type.undef())
            elif ann == 'tuple':
                t = Type.tuple(Type.undef(), Type.ANY_LENGTH)
            elif ann == 'object':
                t = Type.object(None)
            elif ann == 'str':
                t = Type.str()
            elif ann == 'None':
                t = Type.none()
            elif ann == 'generic':
                t = Type.generic()
            elif ann == '...':
                t = Type.ellipsis_t
            else:
                while scope:
                    sym = scope.find_sym(ann)
                    if sym:
                        break
                    else:
                        scope = scope.parent
                if sym and sym.typ.has_scope():
                    sym_scope = sym.typ.get_scope()
                    if sym_scope.is_typeclass():
                        t = Type.from_typeclass(sym_scope)
                    else:
                        t = Type.object(sym_scope)
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
                    t = t.with_length(length)
                else:
                    assert False
                return t
            elif isinstance(first, str):  # in case of Type[T]
                sym = scope.find_sym(first)
                if not sym:
                    raise NameError(first + ' is not defined')
                target_scope = sym.typ.get_scope()
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
                    t = Type.from_typeclass(target_scope, elms)
                    if t.is_seq():
                        t = t.with_length(Type.ANY_LENGTH)
                    return t
        elif ann is None:
            return Type.undef()
        assert False

    @classmethod
    def from_ir(cls, ann, explicit=False):
        from .ir import IR, IRExp, CONST, TEMP, ATTR, MREF, ARRAY, EXPR
        from .symbol import Symbol
        assert ann
        assert isinstance(ann, IR)
        if ann.is_a(CONST) and ann.value is None:
            t = Type.none()
        elif ann.is_a(TEMP) and ann.sym.typ.has_scope():
            scope = ann.sym.typ.get_scope()
            if scope.is_typeclass():
                t = Type.from_typeclass(scope)
                if ann.sym.typ.has_typeargs():
                    args = ann.sym.typ.get_typeargs()
                    t.attrs.update(args)
            else:
                t = Type.object(scope)
        elif ann.is_a(ATTR) and isinstance(ann.attr, Symbol) and ann.attr.typ.has_scope():
            scope = ann.attr.typ.get_scope()
            if scope.is_typeclass():
                t = Type.from_typeclass(scope)
            else:
                t = Type.object(scope)
        elif ann.is_a(MREF):
            if ann.mem.is_a(MREF):
                t = Type.from_ir(ann.mem, explicit)
                if ann.offset.is_a(CONST):
                    t = t.with_length(ann.offset.value)
                else:
                    t = t.with_length(Type.from_ir(ann.offset, explicit))
            else:
                t = Type.from_ir(ann.mem, explicit)
                if t.is_int():
                    assert ann.offset.is_a(CONST)
                    t = t.with_width(ann.offset.value)
                elif t.is_seq():
                    t = t.with_element(Type.from_ir(ann.offset, explicit))
                elif t.is_class():
                    elm_t = Type.from_ir(ann.offset, explicit)
                    if elm_t.is_object():
                        t = t.with_scope(elm_t.get_scope())
                    else:
                        type_scope, args = Type.to_scope(elm_t)
                        t = t.with_scope(type_scope).with_typeargs(args)
        elif ann.is_a(ARRAY):
            assert ann.repeat.is_a(CONST) and ann.repeat.value == 1
            assert ann.is_mutable is False
            # FIXME: tuple should have more than one type
            return Type.from_ir(ann.items[0], explicit)
        else:
            assert ann.is_a(IRExp)
            t = Type.expr(EXPR(ann))
        t = t.with_explicit(explicit)
        return t

    @classmethod
    def from_typeclass(cls, scope, elms=None):
        assert scope.is_typeclass()
        if scope.base_name == 'int':
            return Type.int()
        elif scope.base_name == 'uint':
            return Type.int(signed=False)
        elif scope.base_name == 'bool':
            return Type.bool()
        elif scope.base_name == 'bit':
            return Type.int(1, signed=False)
        elif scope.base_name == 'object':
            return Type.object(None)
        elif scope.base_name == 'generic':
            return Type.generic()
        elif scope.base_name == 'function':
            return Type.function(None)
        elif scope.base_name == 'str':
            return Type.str()
        elif scope.base_name == 'list':
            return Type.list(Type.undef())
        elif scope.base_name == 'tuple':
            return Type.tuple(Type.undef(), Type.ANY_LENGTH)
        elif scope.base_name == 'Type':
            return Type.klass(None)
        elif scope.base_name.startswith('int'):
            return Type.int(int(scope.base_name[3:]))
        elif scope.base_name.startswith('uint'):
            return Type.int(int(scope.base_name[4:]), signed=False)
        elif scope.base_name.startswith('bit'):
            return Type.int(int(scope.base_name[3:]), signed=False)
        elif scope.base_name == ('Int'):
            return Type.int()
        elif scope.base_name == ('List'):
            if elms:
                assert len(elms) == 1
                return Type.list(elms[0])
            else:
                return Type.list(Type.undef())
        elif scope.base_name == ('Tuple'):
            if elms:
                if len(elms) == 2 and elms[1].is_ellipsis():
                    length = Type.ANY_LENGTH
                else:
                    length = len(elms)
                # TODO: multiple type tuple
                return Type.tuple(elms[0], length)
            else:
                return Type.tuple(Type.undef(), Type.ANY_LENGTH)
        else:
            print(scope.name)
            assert False

    @classmethod
    def to_scope(cls, t):
        if t.is_int():
            scope = env.scopes['__builtin__.int']
        elif t.is_bool():
            scope = env.scopes['__builtin__.bool']
        elif t.is_str():
            scope = env.scopes['__builtin__.str']
        elif t.is_list():
            scope = env.scopes['__builtin__.list']
        elif t.is_tuple():
            scope = env.scopes['__builtin__.tuple']
        elif t.is_object():
            scope = env.scopes['__builtin__.object']
        else:
            assert False
        return scope, t.attrs.copy()

    @classmethod
    def from_expr(cls, val, scope):
        if isinstance(val, bool):
            return Type.bool()
        elif isinstance(val, int):
            return Type.int()
        elif isinstance(val, str):
            return Type.str()
        elif isinstance(val, list):
            if len(val):
                elem_t = Type.from_expr(val[0], scope)
            else:
                elem_t = Type.int()
            t = Type.list(elem_t)
            t.attrs['length'] = len(val)
            return t
        elif isinstance(val, tuple):
            if len(val):
                elem_t = Type.from_expr(val[0], scope)
            else:
                elem_t = Type.int()
            t = Type.tuple(elem_t, len(val))
            return t
        elif val is None:
            return Type.none()
        elif hasattr(val, '__class__'):
            t = Type.from_annotation(val.__class__.__name__, scope)
            return t
        else:
            assert False

    def __str__(self):
        if self.name == 'object' and self.get_scope():
            return self.get_scope().base_name
        if env.dev_debug_mode:
            if self.name == 'int':
                if self.get_signed():
                    return f'int{self.get_width()}'
                else:
                    return f'bit{self.get_width()}'
            if self.name == 'list':
                if self.has_length():
                    return f'list<{self.get_element()}, {self.get_length()}, ro:{self.get_ro()}>'
                else:
                    return f'list<{self.get_element()}, ro:{self.get_ro()}>'
            if self.name == 'tuple':
                return f'tuple<{self.get_element()}, {self.get_length()}>'
            if self.name == 'port':
                return f'port<{self.get_dtype()}, {self.get_direction()}>'
            if self.name == 'function':
                if self.get_scope() and self.get_scope().is_method():
                    receiver_name = self.get_scope().parent.base_name
                    return f'function<{receiver_name}>'
                else:
                    return 'function'
            if self.name == 'expr':
                expr = self.get_expr()
                return str(expr)
            if self.name == 'union':
                return f'union<{self.get_types()}>'
        return self.name

    def __repr__(self):
        return f'{self.name}({repr(self.attrs)})'

    def __hash__(self):
        if self.name == 'int':
            return hash((self.name, self.get_width(), self.get_signed()))
        if self.name in ('bool', 'str', 'undef', 'generic', 'none'):
            return hash((self.name,))
        if self.name == 'union':
            hs = tuple([hash(t) for t in self.get_types()])
            return hash(hs)
        if self.name == 'list':
            return hash((hash(self.get_element()), self.get_length()))
        if self.name == 'tuple':
            return hash((hash(self.get_element()), self.get_length()))
        if self.name == 'object':
            return hash((self.name, self.get_scope().name))
        if self.name == 'class':
            return hash((self.name, self.get_scope().name))
        if self.name == 'function':
            return hash((self.name, self.get_scope().name))
        if self.name == 'namespace':
            return hash((self.name, self.get_scope().name))
        if self.name == 'port':
            return hash((self.name, self.get_scope().name))
        return 0

    def __eq__(self, other):
        if not isinstance(other, Type):
            return False
        if self.name != other.name:
            return False
        if self.name == 'int':
            return (self.get_width() == other.get_width()
                    and self.get_signed() == other.get_signed())
        if self.name in ('bool', 'str', 'undef', 'generic', 'none'):
            return True
        if self.name == 'union':
            return self.get_types() == other.get_types()
        if self.name == 'list':
            return (self.get_element() == other.get_element()
                    and self.get_length() == other.get_length()
                    and self.get_ro == other.get_ro())
        if self.name == 'tuple':
            return (self.get_element() == other.get_element()
                    and self.get_length() == other.get_length())
        if self.name == 'object':
            return self.get_scope() is other.get_scope()
        if self.name == 'class':
            if self.get_scope() is not other.get_scope():
                return False
            if len(self.get_typeargs()) != len(other.get_typeargs()):
                return False
            return all([t1 == t2 for t1, t2 in zip(self.get_typeargs(), other.get_typeargs())])
        if self.name == 'function':
            if self.get_scope() is not other.get_scope():
                return False
            if self.get_return_type() != other.get_return_type():
                return False
            if len(self.get_param_types()) != len(other.get_param_types()):
                return False
            return all([pt1 == pt2 for pt1, pt2 in zip(self.get_param_types(), other.get_param_types())])
        if self.name == 'namespace':
            return self.get_scope() is other.get_scope()
        if self.name == 'port':
            return (self.get_scope() is other.get_scope()
                    and self.get_direction() == other.get_direction()
                    and self.get_init() == other.get_init()
                    and self.get_rewritable() == other.get_rewritable()
                    and self.get_root_symbol() == other.get_root_symbol()
                    and self.get_assigned() == other.get_assigned()
                    and self.get_port_kind() == other.get_port_kind())
        return False

    @classmethod
    def undef(cls):
        return Type('undef')

    @classmethod
    def int(cls, width=None, signed=True):
        if width is None:
            width = env.config.default_int_width
        return Type('int', width=width, signed=signed)

    @classmethod
    def bool(cls):
        return Type('bool', width=1)

    @classmethod
    def str(cls):
        return Type('str')

    @classmethod
    def none(cls):
        return Type('none')

    @classmethod
    def generic(cls):
        return Type('generic')

    @classmethod
    def any(cls):
        return Type('any')

    @classmethod
    def list(cls, elm_t, length=ANY_LENGTH):
        #assert elm_t.is_scalar() or elm_t.is_undef()
        return Type('list', element=elm_t, length=length, ro=False)

    @classmethod
    def tuple(cls, elm_t, length):
        #assert elm_t.is_scalar() or elm_t.is_undef()
        return Type('tuple', element=elm_t, length=length)

    @classmethod
    def function(cls, scope, ret_t=None, param_ts=None):
        if ret_t is None:
            ret_t = Type.undef()
        if param_ts is None:
            param_ts = []
        return Type('function', scope=scope, return_type=ret_t, param_types=param_ts)

    @classmethod
    def object(cls, scope):
        return Type('object', scope=scope)

    @classmethod
    def klass(cls, scope, typeargs=None):
        if typeargs is None:
            typeargs = {}
        return Type('class', scope=scope, typeargs=typeargs)

    @classmethod
    def port(cls, portcls, attrs):
        assert isinstance(attrs, dict)
        d = {'scope':portcls}
        d.update(attrs)
        return Type('port', **d)

    @classmethod
    def namespace(cls, scope):
        return Type('namespace', scope=scope)

    @classmethod
    def expr(cls, expr):
        assert expr
        return Type('expr', expr=expr)

    @classmethod
    def union(cls, types):
        raise NotImplementedError()
        assert isinstance(types, set)
        assert all([isinstance(t, Type) for t in types])
        return UnionType(types)

    def is_seq(self):
        return self.name in ('list', 'tuple')

    def is_scalar(self):
        return self.name in ('int', 'bool', 'str')

    def is_containable(self):
        return self.name in ('namespace', 'class')

    @classmethod
    def is_same(cls, t0, t1):
        return t0.name == t1.name

    @classmethod
    def is_assignable(cls, to_t, from_t):
        if from_t.is_any():
            return True
        if to_t is from_t:
            return True
        if to_t.name == from_t.name:
            if to_t.name in ('int', 'bool', 'str'):
                return True
        if to_t == from_t:
            return True
        if to_t.is_int() and from_t.is_bool():
            return True
        if to_t.is_bool() and from_t.is_int():
            return True
        if to_t.is_list() and from_t.is_list():
            if to_t.has_length() and from_t.has_length():
                if to_t.get_length() == from_t.get_length():
                    return True
                elif to_t.get_length() == Type.ANY_LENGTH or from_t.get_length() == Type.ANY_LENGTH:
                    return True
                else:
                    return False
            return True
        if to_t.is_tuple() and from_t.is_tuple():
            return True
        if to_t.is_object() and from_t.is_object():
            to_scope = to_t.get_scope()
            from_scope = from_t.get_scope()
            if to_scope is from_scope:
                return True
            elif to_scope is None or from_scope is None:
                return True
            elif from_scope.is_subclassof(to_scope):
                return True
            return False
        if to_t.is_object() and from_t.is_port() and to_t.get_scope() is from_t.get_scope():
            return True
        if to_t.is_expr():
            from .ir import TEMP, ATTR
            expr = to_t.get_expr()
            if expr.exp.is_a([TEMP, ATTR]) and expr.exp.symbol().typ.is_class():
                return True
        if to_t.is_function() and from_t.is_function():
            if to_t.get_scope() is None:
                return True
        if to_t.is_union():
            return any([cls.is_assignable(t, from_t) for t in to_t.get_types()])
        if from_t.is_union() and len(from_t.get_types()) == 1:
            return any([cls.is_assignable(to_t, t) for t in from_t.get_types()])
        return False

    @classmethod
    def is_compatible(cls, t0, t1):
        return Type.is_assignable(t0, t1) and Type.is_assignable(t1, t0)

    def is_explicit(self):
        return 'explicit' in self.attrs and self.attrs['explicit'] is True

    def is_perfect_explicit(self):
        if self.name in ('list', 'tuple'):
            return self.is_explicit() and self.get_element().is_explicit()
        else:
            return self.is_explicit()

    def with_perfect_explicit(self):
        if self.name in ('list', 'tuple'):
            elm_copy = self.get_element().with_explicit(True)
            copy = self.with_explicit(True).with_element(elm_copy)
        else:
            copy = self.with_explicit(True)
        return copy

    @classmethod
    def propagate(cls, dst, src):
        if dst.is_explicit():
            new_dst = dst
            if dst.is_list():
                assert cls.is_same(dst, src)
                elm = cls.propagate(dst.get_element(), src.get_element())
                new_dst = new_dst.with_element(elm).with_ro(src.get_ro())
                if dst.get_length() == Type.ANY_LENGTH:
                    new_dst = new_dst.with_length(src.get_length())
            elif dst.is_tuple():
                assert cls.is_same(dst, src)
                dst_elm, src_elm = dst.get_element(), src.get_element()
                elm = cls.propagate(dst_elm, src_elm)
                new_dst = new_dst.with_element(elm)
                if dst.get_length() == Type.ANY_LENGTH:
                    new_dst = new_dst.with_length(src.get_length())
            elif dst.is_function():
                assert cls.is_same(dst, src)
                if dst.get_scope() is None:
                    new_dst = new_dst.with_scope(src.get_scope())
                param_types = []
                for pt_dst, pt_src in zip(dst.get_param_types(), src.get_param_types()):
                    param_types.append(cls.propagate(pt_dst, pt_src))
                new_dst = new_dst.with_param_types(param_types)
                ret = cls.propagate(dst.get_return_type(), src.get_return_type())
                new_dst = new_dst.with_return_type(ret)
            elif dst.is_object():
                if cls.is_same(dst, src):
                    if dst.get_scope() is None:
                        new_dst = new_dst.with_scope(src.get_scope())
                    elif dst.get_scope() is src.get_scope().origin:
                        new_dst = new_dst.with_scope(src.get_scope())
                elif src.is_port() and dst.get_scope().is_port():
                    new_dst = src
            elif dst.is_generic():
                return src
            elif dst.is_union():
                raise NotImplementedError()
            return new_dst
        else:
            return src

    @classmethod
    def can_propagate(cls, dst, src):
        if dst.is_undef():
            return True
        elif dst.is_union():
            return True
        elif dst.is_seq() and src.is_seq():
            if cls.can_propagate(dst.get_element(), src.get_element()):
                if (dst.get_length() == src.get_length()
                        or dst.get_length() == Type.ANY_LENGTH):
                    return True
            return False
        return True

    @classmethod
    def find_expr(cls, typ):
        def find_expr_r(typ, exprs):
            if not isinstance(typ, Type):
                return
            if typ.is_expr():
                exprs.append(typ.get_expr())
            elif typ.is_list():
                find_expr_r(typ.get_element(), exprs)
                find_expr_r(typ.get_length(), exprs)
            elif typ.is_tuple():
                find_expr_r(typ.get_element(), exprs)
                find_expr_r(typ.get_length(), exprs)
            elif typ.is_function():
                for pt in typ.get_param_types():
                    find_expr_r(pt, exprs)
                find_expr_r(typ.get_return_type(), exprs)
        exprs = []
        find_expr_r(typ, exprs)
        return exprs

    def with_clone_expr(self):
        copy = Type(self.name, **self.attrs.copy())
        if self.is_expr():
            copy.attrs['expr'] = self.get_expr().clone()
        else:
            for key, v in self.attrs.items():
                if isinstance(v, Type):
                    copy.attrs[key] = v.with_clone_expr()
        return copy

    @classmethod
    def mangled_names(cls, types):
        ts = []
        for t in types:
            if t.is_list():
                elm = cls.mangled_names([t.get_element()])
                if t.get_length() != Type.ANY_LENGTH:
                    s = f'l_{elm}_{t.get_length()}'
                else:
                    s = f'l_{elm}'
            elif t.is_tuple():
                elm = cls.mangled_names([t.get_element()])
                if t.get_length() != Type.ANY_LENGTH:
                    elms = ''.join([elm] * t.get_length())
                else:
                    elms = elm
                s = f't_{elms}'
            elif t.is_class():
                # TODO: we should avoid naming collision
                s = f'c_{t.get_scope().base_name}'
            elif t.is_int():
                s = f'i{t.get_width()}'
                s = 'i'
            elif t.is_bool():
                s = f'b'
            elif t.is_str():
                s = f's'
            elif t.is_object():
                # TODO: we should avoid naming collision
                s = f'o_{t.get_scope().base_name}'
            else:
                s = str(t)
            ts.append(s)
        return '_'.join(ts)

Type.ellipsis_t = Type('ellipsis')


class UnionType(Type):
    def __init__(self, types):
        super().__init__('union')
        self.types = types

    def __getattr__(self, name):
        if name.startswith('is_'):
            typename = name[3:]
            return lambda: self.name == typename
        elif name.startswith('has_'):
            typname = name[4:]
            tnames = [t.name for t in self.types]
            return lambda: typname in tnames
        else:
            raise AttributeError(name)

    def __repr__(self):
        return f'{self.name}({self.types})'

    def __str__(self):
        if env.dev_debug_mode:
            return f'union<{self.types}>'
        return self.name

    def is_seq(self):
        return all([t.name in ('list', 'tuple') for t in self.types])

    def is_scalar(self):
        return all([t.name in ('int', 'bool', 'str') for t in self.types])

    def is_containable(self):
        return all([t.name in ('namespace', 'class') for t in self.types])

    def get_types(self):
        return self.types

    def clone(self):
        return UnionType(self.types.copy())

    def get_element(self):
        assert self.is_seq()
        return UnionType(set([t.get_element() for t in self.types if t.is_seq()]))
