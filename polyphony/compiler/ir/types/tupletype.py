from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from dataclasses import replace as dataclasses_replace
from .type import Type
from ...common.env import env
if TYPE_CHECKING:
    from ..scope import Scope


@dataclass(frozen=True)
class TupleType(Type):
    name: str = field(init=False, default='tuple')
    element: Type
    length: int

    @property
    def scope(self) -> Scope:
        assert '__builtin__.tuple' in env.scopes
        return env.scopes['__builtin__.tuple']

    def clone(self, **args):
        return dataclasses_replace(self, **args)

    def can_assign(self, rhs_t):
        if not rhs_t.is_tuple():
            return False
        elif not self.element.can_assign(rhs_t.element):
            return False
        elif self.length == rhs_t.length or self.length == Type.ANY_LENGTH:
            return True
        else:
            return False

    def propagate(self, rhs_t):
        if not self.can_assign(rhs_t):
            return self
        elm_t = self.element.propagate(rhs_t.element)
        lhs_t = self.clone(element=elm_t)
        if lhs_t.length == Type.ANY_LENGTH:
            lhs_t = lhs_t.clone(length=rhs_t.length)
        return lhs_t

    def __str__(self):
        if env.dev_debug_mode:
            return f'tuple<{self.element}, {self.length}>'
        return self.name
