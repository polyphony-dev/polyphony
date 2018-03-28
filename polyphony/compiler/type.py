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
            if is_lib and ann in env.all_scopes:
                t = Type.object(env.all_scopes[ann])
                t.freeze()
            elif ann == 'int':
                t = Type.int()
                t.freeze()
            elif ann == 'uint':
                t = Type.int(signed=False)
                t.freeze()
            elif ann == 'bool':
                t = Type.bool_t
            elif ann == 'list':
                t = Type.list(Type.int(), None)  # TODO: use Type.any
            elif ann == 'tuple':
                t = Type.tuple(Type.int(), None, Type.ANY_LENGTH)  # TODO: use Type.any
            elif ann == 'object':
                t = Type.object(None)
            elif ann == 'str':
                t = Type.str_t
            elif ann == 'None':
                t = Type.none_t
            elif ann == 'generic':
                t = Type.generic_t
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
                    t.freeze()
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
                    t.freeze()
                    if t.is_seq():
                        t.set_length(Type.ANY_LENGTH)
                    return t
        elif ann is None:
            return Type.undef_t
        assert False

    @classmethod
    def from_typeclass(cls, scope, elms=None):
        assert scope.is_typeclass()
        if scope.orig_name == 'int':
            return Type.int()
        elif scope.orig_name == 'bool':
            return Type.bool_t
        elif scope.orig_name == 'bit':
            return Type.int(1, signed=False)
        elif scope.orig_name.startswith('int'):
            return Type.int(int(scope.orig_name[3:]))
        elif scope.orig_name.startswith('uint'):
            return Type.int(int(scope.orig_name[4:]), signed=False)
        elif scope.orig_name.startswith('bit'):
            return Type.int(int(scope.orig_name[3:]), signed=False)
        elif scope.orig_name == ('List'):
            if elms:
                assert len(elms) == 1
                return Type.list(elms[0], None)
            else:
                # TODO: use Type.any
                return Type.list(Type.int(), None)
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
                return Type.tuple(Type.int(), None, Type.ANY_LENGTH)
        else:
            assert False

    @classmethod
    def from_expr(cls, val, scope):
        if isinstance(val, bool):
            return Type.bool_t
        elif isinstance(val, int):
            return Type.int()
        elif isinstance(val, str):
            return Type.str_t
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
            return Type.none_t
        elif hasattr(val, '__class__'):
            t = Type.from_annotation(val.__class__.__name__, scope)
            t.unfreeze()
            return t
        else:
            assert False

    def __str__(self):
        if self.name == 'object' and self.get_scope():
            return self.get_scope().orig_name
        if env.dev_debug_mode:
            if self.name == 'int':
                return 'int[{}]'.format(self.get_width())
            if self.name == 'list':
                return 'list[{}]'.format(self.get_element())
            if self.name == 'port':
                return 'port[{}, {}]'.format(self.get_dtype(), self.get_direction())
            if self.name == 'function':
                if self.get_scope().is_method():
                    return 'function[{}.{}]'.format(self.get_scope().parent.orig_name, self.get_scope().orig_name)
                else:
                    return 'function[{}]'.format(self.get_scope().orig_name)
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
    def list(cls, elm_t, memnode):
        #assert elm_t.is_scalar() or elm_t.is_undef()
        return Type('list', element=elm_t, memnode=memnode)

    @classmethod
    def tuple(cls, elm_t, memnode, length):
        #assert elm_t.is_scalar() or elm_t.is_undef()
        return Type('tuple', element=elm_t, memnode=memnode, length=length)

    @classmethod
    def function(cls, scope, ret_t, param_ts):
        return Type('function', scope=scope, return_type=ret_t, param_types=param_ts)

    @classmethod
    def object(cls, scope):
        return Type('object', scope=scope)

    @classmethod
    def klass(cls, scope):
        return Type('class', scope=scope)

    @classmethod
    def port(cls, portcls, attrs):
        assert isinstance(attrs, dict)
        d = {'scope':portcls}
        d.update(attrs)
        return Type('port', **d)

    @classmethod
    def namespace(cls, scope):
        return Type('namespace', scope=scope)

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
        if from_t is Type.any_t:
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
                return to_t.get_length() == from_t.get_length()
            return True
        if to_t.is_tuple() and from_t.is_tuple():
            return True
        if to_t.is_object() and from_t.is_object():
            to_scope = to_t.get_scope()
            from_scope = from_t.get_scope()
            if to_scope is from_scope:
                return True
            elif from_scope.is_subclassof(to_scope):
                return True
            return False
        if to_t.is_object() and from_t.is_port() and to_t.get_scope() is from_t.get_scope():
            return True
        if Type.is_strict_same(to_t, from_t):
            return True
        return False

    @classmethod
    def is_compatible(cls, t0, t1):
        return Type.is_assignable(t0, t1) and Type.is_assignable(t1, t0)

    def freeze(self):
        self.attrs['freezed'] = True

    def unfreeze(self):
        if self.is_freezed():
            del self.attrs['freezed']

    def is_freezed(self):
        return 'freezed' in self.attrs and self.attrs['freezed'] is True

    def clone(self):
        if self.name in {'bool', 'str', 'none', 'undef', 'ellipsis', 'generic'}:
            return self
        return Type(self.name, **self.attrs)


Type.bool_t = Type('bool', width=1, freezed=True)
Type.str_t = Type('str', freezed=True)
Type.none_t = Type('none', freezed=True)
Type.undef_t = Type('undef')
Type.ellipsis_t = Type('ellipsis', freezed=True)
Type.generic_t = Type('generic')
Type.any_t = Type('any', freezed=True)