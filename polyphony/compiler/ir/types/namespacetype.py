from dataclasses import dataclass, field
from .scopetype import ScopeType
from ...common.env import env


@dataclass(frozen=True)
class NamespaceType(ScopeType):
    name: str = field(init=False, default='namespace')

    def can_assign(self, rhs_t):
        return False

    def propagate(self, rhs_t):
        return self
