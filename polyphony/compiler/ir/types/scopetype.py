from .type import Type
from ...common.env import env
from ..scope import Scope


class ScopeType(Type):
    def __init__(self, name:str, scope_name: str, explicit=True):
        super().__init__(name, explicit)
        self._scope_name = scope_name

    @property
    def scope(self):
        if self._scope_name not in env.scopes:
            return None
        assert self._scope_name in env.scopes
        return env.scopes[self._scope_name]

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        for k, v in args.items():
            if k == 'scope':
                assert isinstance(v, Scope)
                k = 'scope_name'
                v = v.name
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
            else:
                assert False, f'unknown attribute: {k}'
        return clone

    def __str__(self):
        if env.dev_debug_mode:
            if self.scope:
                return f'{self._name}<{self.scope.unique_name()}>'
            else:
                return f'{self._name}<None>'
        return self._name

    def __hash__(self):
        if self.scope:
            return hash((super().__hash__(), hash(self.scope)))
        else:
            return hash((super().__hash__(),))
