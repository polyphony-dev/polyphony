from .scopetype import ScopeType
from ...common.env import env


class NamespaceType(ScopeType):
    def __init__(self, scope, explicit=True):
        super().__init__('namespace', scope, explicit)
        assert self.scope.is_namespace()

    def can_assign(self, rhs_t):
        return False

    def propagate(self, rhs_t):
        return self
