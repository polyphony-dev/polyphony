from .scopetype import ScopeType
from ...common.env import env


class ObjectType(ScopeType):
    def __init__(self, scope, explicit=True):
        super().__init__('object', scope, explicit)

    def can_assign(self, rhs_t):
        if self._name != rhs_t._name:
            return False
        if self._scope is rhs_t._scope:
            return True
        elif self._scope is None:
            return True
        elif rhs_t._scope and rhs_t._scope.is_subclassof(self._scope):
            return True
        elif rhs_t._scope.is_port() and self._scope.is_port():
            return True
        elif rhs_t.is_port() and self._scope.is_port():
            return True
        return False

    def propagate(self, rhs_t):
        lhs_t = self
        if self._name == rhs_t._name:
            if self._scope is None:
                lhs_t = rhs_t.clone(explicit=self.explicit)
            elif rhs_t._scope and rhs_t._scope.origin is self._scope:
                lhs_t = rhs_t.clone(explicit=self.explicit)
            elif rhs_t._scope.is_port() and self._scope.is_port():
                lhs_t = rhs_t.clone(explicit=self.explicit)
        elif rhs_t.is_port() and self._scope.is_port():
            lhs_t = rhs_t.clone(explicit=self.explicit)
        return lhs_t
