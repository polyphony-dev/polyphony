from .type import Type
from .exprtype import ExprType
from ...common.env import env


class ListType(Type):
    def __init__(self, elm: Type, length: int, explicit=True):
        super().__init__('list', explicit)
        self._element = elm
        self._length= length
        self._ro = False

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
        assert '__builtin__.list' in env.scopes
        return env.scopes['__builtin__.list']

    def is_any_length(self):
        return isinstance(self._length, ExprType) or (isinstance(self._length, int) and self._length == Type.ANY_LENGTH)

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        clone._element = self._element.clone()
        for k, v in args.items():
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
        return clone

    def can_assign(self, rhs_t):
        if not rhs_t.is_list():
            return False
        elif not self._element.can_assign(rhs_t._element):
            return False
        elif isinstance(self._length, int):
            if isinstance(rhs_t._length, int):
                return self._length == rhs_t._length or self._length == Type.ANY_LENGTH or rhs_t._length == Type.ANY_LENGTH
            elif isinstance(rhs_t._length, ExprType):
                return True
        elif isinstance(self._length, ExprType):
            return True
        else:
            return False

    def propagate(self, rhs_t):
        if not self.can_assign(rhs_t):
            return self
        elm_t = self._element.propagate(rhs_t._element)
        lhs_t = self.clone(element=elm_t, ro=rhs_t.ro)
        if lhs_t._length == Type.ANY_LENGTH:
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
