from .type import Type
from ...common.env import env


class ListType(Type):
    def __init__(self, elm, length, explicit=True):
        super().__init__('list', explicit)
        self._element = elm
        self._length= length
        self._ro = False
        self._scope = env.scopes['__builtin__.list']

    @property
    def element(self):
        return self._element

    @property
    def length(self):
        return self._length

    @property
    def ro(self):
        return self._ro

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
        elif self._length == Type.ANY_LENGTH or rhs_t._length == Type.ANY_LENGTH:
            return True
        else:
            return False

    def propagate(self, rhs_t):
        if self._name != rhs_t._name:
            return self
        if not (self._length == rhs_t._length or self._length == Type.ANY_LENGTH):
            return self
        if self._element != rhs_t._element:
            return self
        if self._ro != rhs_t._ro:
            return self
        lhs_t = rhs_t.clone()
        if self._length == Type.ANY_LENGTH:
            lhs_t = lhs_t.clone(length=rhs_t._length)
        return lhs_t

    def __str__(self):
        if env.dev_debug_mode:
            if self._length != Type.ANY_LENGTH:
                return f'list<{self._element}, {self._length}, readonly:{self._ro}>'
            else:
                return f'list<{self._element}, readonly:{self._ro}>'
        return self._name

    def __hash__(self):
        return hash((super().__hash__(), self._element.__hash__()) + (self._length, self._ro))
