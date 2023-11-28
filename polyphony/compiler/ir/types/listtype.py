from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from dataclasses import replace as dataclasses_replace
from .type import Type
from .exprtype import ExprType
from ...common.env import env
if TYPE_CHECKING:
    from ..scope import Scope


@dataclass(frozen=True)
class ListType(Type):
    name: str = field(init=False, default='list')
    element: Type
    length: int | ExprType
    ro: bool

    @property
    def scope(self) -> Scope:
        assert '__builtin__.list' in env.scopes
        return env.scopes['__builtin__.list']

    def is_any_length(self):
        return isinstance(self.length, ExprType) or (isinstance(self.length, int) and self.length == Type.ANY_LENGTH)

    def clone(self, **args):
        return dataclasses_replace(self, **args)

    def can_assign(self, rhs_t):
        if not rhs_t.is_list():
            return False
        elif not self.element.can_assign(rhs_t.element):
            return False
        elif isinstance(self.length, int):
            if isinstance(rhs_t.length, int):
                return self.length == rhs_t.length or self.length == Type.ANY_LENGTH or rhs_t.length == Type.ANY_LENGTH
            elif isinstance(rhs_t.length, ExprType):
                return True
        elif isinstance(self.length, ExprType):
            return True
        else:
            return False

    def propagate(self, rhs_t):
        if not self.can_assign(rhs_t):
            return self
        elm_t = self.element.propagate(rhs_t.element)
        lhs_t = self.clone(element=elm_t, ro=rhs_t.ro)
        if lhs_t.length == Type.ANY_LENGTH:
            lhs_t = lhs_t.clone(length=rhs_t.length)
        return lhs_t

    def __str__(self):
        if env.dev_debug_mode:
            if self.length != Type.ANY_LENGTH:
                return f'list<{self.element}, {self.length}, readonly:{self.ro}>'
            else:
                return f'list<{self.element}, readonly:{self.ro}>'
        return self.name
