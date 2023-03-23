from .type import Type
from .scopetype import ScopeType
from ...common.env import env


class FunctionType(ScopeType):
    def __init__(self, scope, ret_t, param_ts, explicit=True):
        super().__init__('function', scope, explicit)
        assert not scope or scope.is_function() or scope.is_method()
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
        return self._name == rhs_t._name and self._scope is None

    def propagate(self, rhs_t):
        lhs_t = self
        if lhs_t._name == rhs_t._name:
            if lhs_t._scope is None:
                lhs_t = rhs_t.clone(explicit=self.explicit)
            if not lhs_t.explicit and rhs_t.explicit and lhs_t._scope is rhs_t._scope:
                param_types = [t.clone(explicit=False) for t in rhs_t._param_types]
                lhs_t = lhs_t.clone(param_types=param_types, return_type=rhs_t._return_type.clone())
        return lhs_t

    def __hash__(self):
        if self._scope:
            params = [hash(t) for t in self._param_types]
            return hash((super().__hash__(), hash(self._scope), hash(self._return_type)) + tuple(params))
        else:
            return hash((super().__hash__(), hash(self._scope)))