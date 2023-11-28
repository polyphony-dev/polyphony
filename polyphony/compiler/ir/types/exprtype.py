from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from dataclasses import replace as dataclasses_replace
from .type import Type
from ...common.env import env
if TYPE_CHECKING:
    from ..ir import EXPR


@dataclass(frozen=True)
class ExprType(Type):
    name: str = field(init=False, default='expr')
    expr: EXPR

    def clone(self, **args):
        return dataclasses_replace(self, **args)

    def can_assign(self, rhs_t):
        return self.name == rhs_t.name and self.expr == rhs_t.expr

    def propagate(self, rhs_t):
        return self

    def __str__(self):
        if env.dev_debug_mode:
            return f'expr<{self.expr}>'
        return self.name
