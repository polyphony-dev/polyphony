from .scopetype import ScopeType
from ...common.env import env


class ObjectType(ScopeType):
    def __init__(self, scope_name, explicit=True):
        super().__init__('object', scope_name, explicit)
        assert self.scope.is_class()

    def can_assign(self, rhs_t):
        if self.scope.is_object():
            return not (rhs_t.is_undef() or rhs_t.is_class() or rhs_t.is_function() or rhs_t.is_namespace() or rhs_t.is_expr())
        elif self._name != rhs_t._name:
            return False
        elif self.scope is rhs_t.scope:
            return True
        elif self.scope is rhs_t.scope.origin:
            return True
        elif rhs_t.scope.is_subclassof(self.scope):
            return True
        elif rhs_t.scope.is_port() and self.scope.is_port():
            return True
        elif rhs_t.is_port() and self.scope.is_port():
            return True
        return False

    def propagate(self, rhs_t):
        lhs_t = self
        if self._name == rhs_t._name:
            if self.scope.is_object():
                lhs_t = rhs_t.clone(explicit=self.explicit)
            elif rhs_t.scope.origin is self.scope:
                lhs_t = rhs_t.clone(explicit=self.explicit)
            elif rhs_t.scope.is_port() and self.scope.is_port():
                lhs_t = rhs_t.clone(explicit=self.explicit)
        elif rhs_t.is_port() and self.scope.is_port():
            lhs_t = rhs_t.clone(explicit=self.explicit)
        elif self.scope.is_object():
            if not (rhs_t.is_undef() or rhs_t.is_class() or rhs_t.is_function() or rhs_t.is_namespace() or rhs_t.is_expr()):
                lhs_t = rhs_t.clone(explicit=self.explicit)
        return lhs_t
