from .type import Type
from ...common.env import env
from ..scope import Scope

class SimpleType(Type):
    def __init__(self, name: str, scope_name: str, explicit=True):
        super().__init__(name, explicit)
        self._scope_name = scope_name

    @property
    def scope(self) -> Scope:
        assert self._scope_name in env.scopes
        return env.scopes[self._scope_name]

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        for k, v in args.items():
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
        return clone

    def can_assign(self, rhs_t) -> bool:
        return self._name == rhs_t._name

    def propagate(self, rhs_t) -> Type:
        if self._name == rhs_t._name and rhs_t._explicit:
            return rhs_t.clone(explicit=self.explicit)
        return self
