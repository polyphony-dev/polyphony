from .type import Type
from ...common.env import env


class TupleType(Type):
    def __init__(self, elm, length, explicit=True):
        super().__init__('tuple', explicit)
        self._element = elm
        self._length= length
        self._scope = env.scopes['__builtin__.tuple']

    @property
    def element(self):
        return self._element

    @property
    def length(self):
        return self._length

    @property
    def scope(self):
        return self._scope

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        clone._element = self._element.clone()
        for k, v in args.items():
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
        return clone

    def can_assign(self, rhs_t):
        if not rhs_t.is_tuple():
            return False
        elif not self._element.can_assign(rhs_t._element):
            return False
        elif self._length == rhs_t._length or self._length == Type.ANY_LENGTH:
            return True
        else:
            return False

    def propagate(self, rhs_t):
        if not self.can_assign(rhs_t):
            return self
        elm_t = self._element.propagate(rhs_t._element)
        lhs_t = self.clone(element=elm_t)
        if lhs_t._length == Type.ANY_LENGTH:
            lhs_t = lhs_t.clone(length=rhs_t._length)
        return lhs_t

    def __str__(self):
        if env.dev_debug_mode:
            return f'tuple<{self._element}, {self._length}>'
        return self._name

    def __hash__(self):
        return hash((super().__hash__(), self._element.__hash__()) + (self._length,))
