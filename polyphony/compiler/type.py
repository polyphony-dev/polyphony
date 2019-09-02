from .env import env


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
        elif name.startswith('set_'):
            attrname = name[4:]
            return lambda v: self.attrs.update({attrname:v})
        elif name.startswith('has_'):
            attrname = name[4:]
            return lambda: attrname in self.attrs
        else:
            raise AttributeError(name)

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
                t = Type.list(Type.undef_t, None)  # TODO: use Type.any
            elif ann == 'tuple':
                t = Type.tuple(Type.undef_t, None, Type.ANY_LENGTH)  # TODO: use Type.any
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
                    t.set_length(length)
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
                    elif not all([Type.is_strict_same(elms[0], elm) for elm in elms[1:]]):
                        raise TypeError('multiple type tuple is not supported yet')
                elif isinstance(second, str):
                    elms = [Type.from_annotation(second, scope)]
                else:
                    assert False
                if target_scope.is_typeclass():
                    t = Type.from_typeclass(target_scope, elms)
                    if t.is_seq():
                        t.set_length(Type.ANY_LENGTH)
                    return t
        elif ann is None:
            return Type.undef_t
        assert False

    @classmethod
    def from_ir(cls, ann):
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
                t = Type.from_ir(ann.mem)
                if ann.offset.is_a(CONST):
                    t.set_length(ann.offset.value)
                else:
                    t.set_length(Type.from_ir(ann.offset))
            else:
                t = Type.from_ir(ann.mem)
                if t.is_int():
                    assert ann.offset.is_a(CONST)
                    t.set_width(ann.offset.value)
                elif t.is_seq():
                    t.set_element(Type.from_ir(ann.offset))
                elif t.is_class():
                    elm_t = Type.from_ir(ann.offset)
                    if elm_t.is_object():
                        t.set_scope(elm_t.get_scope())
                    else:
                        type_scope, args = Type.to_scope(elm_t)
                        t.set_scope(type_scope)
                        t.set_typeargs(args)
        elif ann.is_a(ARRAY):
            assert ann.repeat.is_a(CONST) and ann.repeat.value == 1
            assert ann.is_mutable is False
            # FIXME: tuple should have more than one type
            return Type.from_ir(ann.items[0])
        else:
            assert ann.is_a(IRExp)
            t = Type.expr(EXPR(ann))
        t.set_explicit(True)
        return t

    @classmethod
    def from_typeclass(cls, scope, elms=None):
        assert scope.is_typeclass()
        if scope.orig_name == 'int':
            return Type.int()
        elif scope.orig_name == 'uint':
            return Type.int(signed=False)
        elif scope.orig_name == 'bool':
            return Type.bool()
        elif scope.orig_name == 'bit':
            return Type.int(1, signed=False)
        elif scope.orig_name == 'object':
            return Type.object(None)
        elif scope.orig_name == 'generic':
            return Type.generic()
        elif scope.orig_name == 'function':
            return Type.function(None)
        elif scope.orig_name == 'str':
            return Type.str()
        elif scope.orig_name == 'list':
            return Type.list(Type.undef_t, None)
        elif scope.orig_name == 'tuple':
            return Type.tuple(Type.undef_t, None, Type.ANY_LENGTH)
        elif scope.orig_name == 'Type':
            return Type.klass(None)
        elif scope.orig_name.startswith('int'):
            return Type.int(int(scope.orig_name[3:]))
        elif scope.orig_name.startswith('uint'):
            return Type.int(int(scope.orig_name[4:]), signed=False)
        elif scope.orig_name.startswith('bit'):
            return Type.int(int(scope.orig_name[3:]), signed=False)
        elif scope.orig_name == ('Int'):
            return Type.int()
        elif scope.orig_name == ('List'):
            if elms:
                assert len(elms) == 1
                return Type.list(elms[0], None)
            else:
                # TODO: use Type.any
                return Type.list(Type.undef_t, None)
        elif scope.orig_name == ('Tuple'):
            if elms:
                if len(elms) == 2 and elms[1].is_ellipsis():
                    length = Type.ANY_LENGTH
                else:
                    length = len(elms)
                # TODO: multiple type tuple
                return Type.tuple(elms[0], None, length)
            else:
                # TODO: use Type.any
                return Type.tuple(Type.undef_t, None, Type.ANY_LENGTH)
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
            t = Type.list(elem_t, None)
            t.attrs['length'] = len(val)
            return t
        elif isinstance(val, tuple):
            if len(val):
                elem_t = Type.from_expr(val[0], scope)
            else:
                elem_t = Type.int()
            t = Type.tuple(elem_t, None, len(val))
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
            return self.get_scope().orig_name
        if env.dev_debug_mode:
            if self.name == 'int':
                return 'int{}'.format(self.get_width())
            if self.name == 'list':
                if self.has_length():
                    return 'list<{}><{}>'.format(self.get_element(), self.get_length())
                else:
                    return 'list<{}>'.format(self.get_element())
            if self.name == 'port':
                return 'port<{}, {}>'.format(self.get_dtype(), self.get_direction())
            if self.name == 'function':
                if self.get_scope().is_method():
                    return 'function<{}.{}>'.format(self.get_scope().parent.orig_name, self.get_scope().orig_name)
                else:
                    return 'function<{}>'.format(self.get_scope().orig_name)
            if self.name == 'expr':
                expr = self.get_expr()
                return str(expr)
        return self.name

    def __repr__(self):
        return 'Type({}, {})'.format(repr(self.name), repr(self.attrs))

    @classmethod
    def int(cls, width=None, signed=True):
        if width is None:
            width = env.config.default_int_width
        return Type('int', width=width, signed=signed)

    @classmethod
    def wider_int(clk, t0, t1):
        if t0.is_int() and t1.is_int():
            return t0 if t0.get_width() >= t1.get_width() else t1
        else:
            return t0

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
    def list(cls, elm_t, memnode, length=ANY_LENGTH):
        #assert elm_t.is_scalar() or elm_t.is_undef()
        return Type('list', element=elm_t, memnode=memnode, length=length)

    @classmethod
    def tuple(cls, elm_t, memnode, length):
        #assert elm_t.is_scalar() or elm_t.is_undef()
        return Type('tuple', element=elm_t, memnode=memnode, length=length)

    @classmethod
    def function(cls, scope, ret_t=None, param_ts=None):
        if ret_t is None:
            ret_t = Type.undef_t
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
    def channel(cls, chancls, attrs):
        assert isinstance(attrs, dict)
        d = {'scope':chancls}
        d.update(attrs)
        return Type('channel', **d)

    @classmethod
    def namespace(cls, scope):
        return Type('namespace', scope=scope)

    @classmethod
    def expr(cls, expr):
        assert expr
        return Type('expr', expr=expr)

    def is_seq(self):
        return self.name == 'list' or self.name == 'tuple' or self.name == 'any'

    def is_scalar(self):
        return self.name == 'int' or self.name == 'bool' or self.name == 'str' or self.name == 'any'

    def is_containable(self):
        return self.name == 'namespace' or self.name == 'class'

    @classmethod
    def is_same(cls, t0, t1):
        return t0.name == t1.name

    @classmethod
    def is_strict_same(cls, t0, t1):
        if t0.name != t1.name:
            return False
        if t0.is_int():
            return t0.get_width() == t1.get_width() and t0.get_signed() == t1.get_signed()
        return True

    @classmethod
    def is_assignable(cls, to_t, from_t):
        if from_t.is_any():
            return True
        if to_t is from_t:
            return True
        if to_t.is_int() and from_t.is_int():
            return True
        if to_t.is_int() and from_t.is_bool():
            return True
        if to_t.is_bool() and from_t.is_int():
            return True
        if to_t.is_str() and from_t.is_str():
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
        if Type.is_strict_same(to_t, from_t):
            return True
        if to_t.is_expr():
            from .ir import TEMP, ATTR
            expr = to_t.get_expr()
            if expr.exp.is_a([TEMP, ATTR]) and expr.exp.symbol().typ.is_class():
                return True
        return False

    @classmethod
    def is_compatible(cls, t0, t1):
        return Type.is_assignable(t0, t1) and Type.is_assignable(t1, t0)

    def is_explicit(self):
        return 'explicit' in self.attrs and self.attrs['explicit'] is True

    def clone(self):
        if self.name in {'undef', 'ellipsis'}:
            t = self
        elif self.is_list():
            t = Type(self.name, **self.attrs)
            t.set_element(t.get_element().clone())
            if isinstance(t.get_length(), Type):
                t.set_length(t.get_length().clone())
        elif self.is_tuple():
            t = Type(self.name, **self.attrs)
            t.set_element(t.get_element().clone())
            if isinstance(t.get_length(), Type):
                t.set_length(t.get_length().clone())
        elif self.is_function():
            t = Type(self.name, **self.attrs)
            t.set_return_type(t.get_return_type().clone())
            param_types = [pt.clone() for pt in t.get_param_types()]
            t.set_param_types(param_types)
        elif self.is_expr():
            t = Type(self.name, **self.attrs)
            t.set_expr(t.get_expr().clone())
        else:
            t = Type(self.name, **self.attrs)
        return t

    @classmethod
    def propagate(cls, dst, src):
        if dst.is_explicit():
            if dst.is_list():
                assert cls.is_same(dst, src)
                elm = cls.propagate(dst.get_element(), src.get_element())
                dst.set_element(elm)
                if dst.get_length() == Type.ANY_LENGTH:
                    dst.set_length(src.get_length())
            elif dst.is_tuple():
                assert cls.is_same(dst, src)
                dst_elm, src_elm = dst.get_element(), src.get_element()
                elm = cls.propagate(dst_elm, src_elm)
                dst.set_element(elm)
                if dst.get_length() == Type.ANY_LENGTH:
                    dst.set_length(src.get_length())
            elif dst.is_function():
                assert cls.is_same(dst, src)
                if dst.get_scope() is None:
                    dst.set_scope(src.get_scope())
                param_types = []
                for pt_dst, pt_src in zip(dst.get_param_types(), src.get_param_types()):
                    param_types.append(cls.propagate(pt_dst, pt_src))
                dst.set_param_types(param_types)
                ret = cls.propagate(dst.get_return_type(), src.get_return_type())
                dst.set_return_type(ret)
            elif dst.is_object():
                assert cls.is_same(dst, src)
                if dst.get_scope() is None:
                    dst.set_scope(src.get_scope())
            return dst
        else:
            return src

    @classmethod
    def can_propagate(cls, dst, src):
        if dst.is_undef():
            return True
        elif dst.is_seq() and src.is_seq():
            if dst.get_memnode() is src.get_memnode():
                return True
            elif dst.get_memnode() is None:
                return True
            elif src.get_memnode() and dst.get_memnode().sym is src.get_memnode().sym:
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


Type.undef_t = Type('undef')
Type.ellipsis_t = Type('ellipsis')
