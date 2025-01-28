from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from dataclasses import replace as dataclasses_replace
from .scopetype import ScopeType
from ...common.env import env
if TYPE_CHECKING:
    from ..ir import EXPR


@dataclass(frozen=True)
class ExprType(ScopeType):
    name: str = field(init=False, default='expr')
    expr: EXPR

    def can_assign(self, rhs_t):
        return self.name == rhs_t.name

    def propagate(self, rhs_t):
        return rhs_t

    def __str__(self):
        if env.dev_debug_mode:
            return f'expr<{self.expr}>{self.scope_name}'
        return self.name
