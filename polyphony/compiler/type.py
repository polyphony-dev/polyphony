import ast

class Type:
    @classmethod
    def from_annotation(cls, ann):
        if isinstance(ann, ast.Name):
            if ann.id == 'int':
                return Type.int_t
            elif ann.id == 'list':
                return cls.list(cls.int_t, None)
            elif ann.id == 'object':
                return cls.object(None, None)
        return Type.int_t

    int_t = ('int',)
    bool_t = ('bool',)
    none_t = ('none',)

    @classmethod
    def str(cls, t):
        if t is cls.int_t: return 'i'
        elif t is cls.bool_t: return 'b'
        elif t is cls.none_t: return 'n'
        elif cls.is_list(t):
            return 'l'
        elif cls.is_object(t):
            return 'o'
        elif cls.is_class(t):
            return 'c'
        else:
            return 'n'
    @classmethod
    def list(cls, src_typ, memnode):
        assert src_typ is cls.int_t or src_typ is cls.bool_t
        return ('list', src_typ, memnode)

    @classmethod
    def tuple(cls, src_typ, memnode):
        assert src_typ is cls.int_t or src_typ is cls.bool_t
        return ('tuple', src_typ, memnode)

    @classmethod
    def function(cls, ret_typ, param_types):
        return ('func', ret_typ, param_types)

    @classmethod
    def object(cls, src_typ, scope):
        return ('object', src_typ, scope)

    @classmethod
    def klass(cls, src_typ, scope):
        return ('class', src_typ, scope)

    @classmethod
    def is_none(cls, t):
        return t is cls.none_t

    @classmethod
    def is_int(cls, t):
        return t is cls.int_t

    @classmethod
    def is_list(cls, t):
        return isinstance(t, tuple) and t[0] == 'list'

    @classmethod
    def is_tuple(cls, t):
        return isinstance(t, tuple) and t[0] == 'tuple'

    @classmethod
    def is_seq(cls, t):
        return cls.is_list(t) or cls.is_tuple(t)

    @classmethod
    def is_scalar(cls, t):
        return t is cls.int_t or t is cls.bool_t

    @classmethod
    def is_function(cls, t):
        return isinstance(t, tuple) and t[0] == 'func'

    @classmethod
    def is_object(cls, t):
        return isinstance(t, tuple) and t[0] == 'object'

    @classmethod
    def is_class(cls, t):
        return isinstance(t, tuple) and t[0] == 'class'

    @classmethod
    def is_commutable(cls, t0, t1):
        if t0 is t1:
            return True
        if t0 is cls.bool_t and t1 is cls.int_t or t0 is cls.int_t and t1 is cls.bool_t:
            return True
        if cls.is_list(t0) and cls.is_list(t1):
            return True
        return False

    @classmethod
    def element(cls, t):
        if cls.is_list(t):
            return t[1]
        else:
            return t

    @classmethod
    def extra(cls, t):
        if cls.is_list(t) or cls.is_class(t) or cls.is_object(t):
            return t[2]
        return None

