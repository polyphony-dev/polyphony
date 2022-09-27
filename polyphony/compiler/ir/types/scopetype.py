from .type import Type
from ...common.env import env


class ScopeType(Type):
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

    def __str__(self):
        if env.dev_debug_mode:
            if self._scope:
                return f'{self._name}<{self._scope.name}>'
            else:
                return f'{self._name}<None>'
        return self._name

    def __hash__(self):
        if self._scope:
            return hash((super().__hash__(), hash(self._scope)))
        else:
            return hash((super().__hash__(),))
