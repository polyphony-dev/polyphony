from .scopetype import ScopeType
from ...common.env import env


class ClassType(ScopeType):
    def __init__(self, scope, explicit=True):
        super().__init__('class', scope, explicit)
        assert not scope or scope.is_class() or scope.is_typeclass()

    def can_assign(self, rhs_t):
        return self._name == rhs_t._name and self._scope is rhs_t._scope

    def propagate(self, rhs_t):
        if self._name == rhs_t._name and self._scope is None:
            return rhs_t.clone()
        else:
            return self
