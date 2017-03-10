from .env import env

class Type(object):
    DEFAULT_INT_WIDTH = 32

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
    def from_annotation(cls, ann, scope):
        if isinstance(ann, str):
            if ann == 'int':
                t = Type.int()
                t.freeze()
            elif ann == 'uint':
                t = Type.int(signed=False)
                t.freeze()
            elif ann == 'bool':
                t = Type.bool_t
            elif ann == 'list':
                t = Type.list(Type.int(), None)
            elif ann == 'tuple':
                t = Type.tuple(Type.int(), None, 0)
            elif ann == 'object':
                t = Type.object(None)
            elif ann == 'str':
                t = Type.str_t
            elif ann in env.all_scopes:
                t = Type.object(env.all_scopes[ann])
                t.freeze()
            return t
        elif isinstance(ann, tuple):
            qnames = ann[0].split('.')
            args = ann[1]
            target = scope
            for qname in qnames:
                sym = target.find_sym(qname)
                if not sym or (not sym.typ.is_namespace() and not sym.typ.is_class()):
                    return None
                target = sym.typ.get_scope()
                if not target:
                    return None
            if target.is_port():
                ctor = target.find_ctor()
                attrs = {}
                for i, (_, copy, defval) in enumerate(ctor.params[1:]):
                    if i >= len(args):
                        attrs[copy.name] = defval.value
                    else:
                        attrs[copy.name] = args[i]
                p = Type.port(target, attrs)
                return p
        elif ann is None:
            return Type.undef_t
        assert False

    def __str__(self):
        return self.name

    def __repr__(self):
        return 'Type({}, {})'.format(repr(self.name), repr(self.attrs))

    @classmethod
    def int(cls, width=DEFAULT_INT_WIDTH, signed=True):
        return Type('int', width=width, signed=signed)

    @classmethod
    def wider_int(clk, t0, t1):
        if t0.is_int() and t1.is_int():
            return t0 if t0.get_width() >= t1.get_width() else t1
        else:
            return t0

    @classmethod
    def list(cls, elm_t, memnode):
        assert elm_t.is_scalar()
        return Type('list', element=elm_t, memnode=memnode)

    @classmethod
    def tuple(cls, elm_t, memnode, length):
        assert elm_t.is_scalar()
        return Type('tuple', element=elm_t, memnode=memnode, length=length)

    @classmethod
    def function(cls, scope, ret_t, param_ts):
        return Type('function', scope=scope, retutn_type=ret_t, param_types=param_ts)

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
        return self.name == 'list' or self.name == 'tuple'

    def is_scalar(self):
        return self.name == 'int' or self.name == 'bool' or self.name == 'str'

    def is_containable(self):
        return self.name == 'namespace' or self.name == 'class'

    @classmethod
    def is_same(cls, t0, t1):
        return t0.name == t1.name

    @classmethod
    def can_overwrite(cls, to_t, from_t):
        if to_t is from_t:
            return True
        if to_t.is_int() and from_t.is_int():
            return True
        if to_t.is_int() and from_t.is_bool():
            return True
        if to_t.is_list() and from_t.is_list():
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
        if to_t == from_t:
            return True
        return False

    @classmethod
    def is_commutable(cls, t0, t1):
        if t0 is t1:
            return True
        if t0.is_int() and t1.is_int():
            return True
        if t0.is_bool() and t1.is_int() or t0.is_int() and t1.is_bool():
            return True
        if t0.is_list() and t1.is_list():
            return True
        if t0.is_tuple() and t1.is_tuple():
            return True
        if t0.is_object() and t1.is_object() and t0.get_scope() is t1.get_scope():
            return True
        if t0.is_object() and t1.is_port() and t0.get_scope() is t1.get_scope():
            return True
        if t1.is_object() and t0.is_port() and t0.get_scope() is t1.get_scope():
            return True
        if t0 == t1:
            return True
        return False

    def freeze(self):
        self.attrs['freezed'] = True

    def is_freezed(self):
        return 'freezed' in self.attrs and self.attrs['freezed'] is True

    def clone(self):
        return Type(self.name, **self.attrs)


Type.bool_t = Type('bool', width=1, freezed=True)
Type.str_t = Type('str', freezed=True)
Type.none_t = Type('none', freezed=True)
Type.undef_t = Type('undef')