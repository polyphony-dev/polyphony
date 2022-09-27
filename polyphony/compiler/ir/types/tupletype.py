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
        if not rhs_t.is_seq():
            return False
        elif self._length == rhs_t._length:
            return True
        else:
            return False

    def propagate(self, rhs_t):
        if self._name != rhs_t._name:
            return self
        if not (self._length == rhs_t._length or self._length == Type.ANY_LENGTH):
            return self.clone()
        if self._element != rhs_t._element:
            return self
        return rhs_t.clone()

    def __str__(self):
        if env.dev_debug_mode:
            return f'tuple<{self._element}, {self._length}>'
        return self._name

    def __hash__(self):
        return hash((super().__hash__(), self._element.__hash__()) + (self._length,))
