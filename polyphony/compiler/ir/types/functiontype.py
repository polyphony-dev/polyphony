from .type import Type
from .scopetype import ScopeType
from ...common.env import env


class FunctionType(ScopeType):
    def __init__(self, scope_name: str, ret_t: Type, param_ts: tuple, explicit=True):
        super().__init__('function', scope_name, explicit)
        assert self.scope.is_function() or self.scope.is_method() or self.scope.is_object()
        self._return_type = ret_t
        assert isinstance(param_ts, (list, tuple))
        self._param_types = param_ts

    @property
    def return_type(self):
        return self._return_type

    @property
    def param_types(self):
        return self._param_types

    def can_assign(self, rhs_t):
        return self._name == rhs_t._name and self.scope.is_object()

    def propagate(self, rhs_t):
        lhs_t = self
        if lhs_t._name == rhs_t._name:
            if lhs_t.scope.is_object():
                lhs_t = rhs_t.clone(explicit=self.explicit)
            if not lhs_t.explicit and rhs_t.explicit and lhs_t.scope is rhs_t.scope:
                param_types = [t.clone(explicit=False) for t in rhs_t._param_types]
                lhs_t = lhs_t.clone(param_types=param_types, return_type=rhs_t._return_type.clone())
        return lhs_t

    def __hash__(self):
        if self.scope:
            params = [hash(t) for t in self._param_types]
            return hash((super().__hash__(), hash(self.scope), hash(self._return_type)) + tuple(params))
        else:
            assert False
            return hash((super().__hash__(), hash(self.scope)))