from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from dataclasses import replace as dataclasses_replace
from .type import Type
from ...common.env import env
if TYPE_CHECKING:
    from ..scope import Scope


@dataclass(frozen=True)
class ScopeType(Type):
    scope_name: str

    @property
    def scope(self) -> Scope:
        assert self.scope_name in env.scopes
        return env.scopes[self.scope_name]

    def clone(self, **args):
        from ..scope import Scope
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
                return f'{self.name}<{self.scope.name}>'
            else:
                return f'{self.name}<None>'
        return self.name
