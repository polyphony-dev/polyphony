from dataclasses import dataclass
from dataclasses import replace as dataclasses_replace
from .type import Type
from ...common.env import env
from ..scope import Scope


@dataclass(frozen=True)
class ScopeType(Type):
    scope_name: str

    @property
    def scope(self):
        assert self.scope_name in env.scopes
        return env.scopes[self.scope_name]

    def clone(self, **args):
        new_args = {}
        for k, v in args.items():
            if k == 'scope':
                assert isinstance(v, Scope)
                k = 'scope_name'
                v = v.name
            new_args[k] = v
        return dataclasses_replace(self, **new_args)

    def __str__(self):
        if env.dev_debug_mode:
            if self.scope:
                return f'{self.name}<{self.scope.unique_name()}>'
            else:
                return f'{self.name}<None>'
        return self.name
