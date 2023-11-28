from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from dataclasses import replace as dataclasses_replace
from .type import Type
from ...common.env import env
if TYPE_CHECKING:
    from ..scope import Scope


@dataclass(frozen=True)
class IntType(Type):
    name: str = field(init=False, default='int')
    width: int
    signed: bool

    @property
    def scope(self) -> Scope:
        assert '__builtin__.int' in env.scopes
        return env.scopes['__builtin__.int']

    def clone(self, **args):
        return dataclasses_replace(self, **args)

    def can_assign(self, rhs_t):
        return (self.name == rhs_t.name
            or rhs_t.is_bool())

    def propagate(self, rhs_t):
        lhs_t = self
        if self.name == rhs_t.name:
            if not self.explicit:
                lhs_t = rhs_t.clone(explicit=self.explicit)
        return lhs_t

    def __str__(self):
        if self.signed:
            return f'int{self.width}'
        else:
            return f'bit{self.width}'
