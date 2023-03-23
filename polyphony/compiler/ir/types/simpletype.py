from .type import Type
from ...common.env import env


class SimpleType(Type):
    def __init__(self, name, scope, explicit=True):
        super().__init__(name, explicit)
        self._scope = scope

    @property
    def scope(self):
        return self._scope

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        for k, v in args.items():
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
        return clone

    def can_assign(self, rhs_t):
        return self._name == rhs_t._name

    def propagate(self, rhs_t):
        if self._name == rhs_t._name and rhs_t._explicit:
            return rhs_t.clone(explicit=self.explicit)
        return self
