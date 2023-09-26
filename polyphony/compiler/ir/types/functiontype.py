from dataclasses import dataclass, field
from .type import Type
from .scopetype import ScopeType
from ...common.env import env


@dataclass(frozen=True)
class FunctionType(ScopeType):
    name: str = field(init=False, default='function')
    return_type: Type
    param_types: list[Type]

    def __post_init__(self):
        assert self.scope.is_function() or self.scope.is_method() or self.scope.is_object()

    def can_assign(self, rhs_t):
        return self.name == rhs_t.name and self.scope.is_object()

    def propagate(self, rhs_t):
        lhs_t = self
        if lhs_t.name == rhs_t.name:
            if lhs_t.scope.is_object():
                lhs_t = rhs_t.clone(explicit=self.explicit)
            if not lhs_t.explicit and rhs_t.explicit and lhs_t.scope is rhs_t.scope:
                param_types = [t.clone(explicit=False) for t in rhs_t.param_types]
                lhs_t = lhs_t.clone(param_types=param_types, return_type=rhs_t.return_type.clone())
        return lhs_t
