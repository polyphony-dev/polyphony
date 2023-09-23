from .type import Type
from ...common.env import env


class IntType(Type):
    def __init__(self, width, signed, explicit):
        super().__init__('int', explicit)
        self._width = width
        self._signed = signed

    @property
    def width(self):
        return self._width

    @property
    def signed(self):
        return self._signed

    @property
    def scope(self):
        assert '__builtin__.int' in env.scopes
        return env.scopes['__builtin__.int']

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        for k, v in args.items():
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
        return clone

    def can_assign(self, rhs_t):
        return (self._name == rhs_t._name
            or rhs_t.is_bool())

    def propagate(self, rhs_t):
        lhs_t = self
        if self._name == rhs_t._name:
            if not self.explicit:
                lhs_t = rhs_t.clone(explicit=self.explicit)
        return lhs_t

    def __str__(self):
        if self._signed:
            return f'int{self._width}'
        else:
            return f'bit{self._width}'

    def __hash__(self):
        return hash((super().__hash__(),) + (self._width, self._signed))
