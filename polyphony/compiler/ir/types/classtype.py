from .scopetype import ScopeType
from ...common.env import env


class ClassType(ScopeType):
    def __init__(self, scope_name, explicit=True):
        super().__init__('class', scope_name, explicit)
        assert self.scope.is_class() or self.scope.is_typeclass()

    def can_assign(self, rhs_t):
        return self._name == rhs_t._name and (self.scope is rhs_t.scope or self.scope.is_object())

    def propagate(self, rhs_t):
        if self._name == rhs_t._name and self.scope.is_object():
            return rhs_t.clone(explicit=self.explicit)
        else:
            return self
