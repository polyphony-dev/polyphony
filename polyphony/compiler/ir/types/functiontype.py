from dataclasses import dataclass, field
from .type import Type
from .scopetype import ScopeType


@dataclass(frozen=True)
class FunctionType(ScopeType):
    name: str = field(init=False, default='function')
    return_type: Type
    param_types: tuple[Type, ...]

    def __post_init__(self):
        assert self.scope.is_function() or self.scope.is_method() or self.scope.is_object()

    def can_assign(self, rhs_t):
        if self.name != rhs_t.name:
            return False
        if self.scope.is_object():
            return True
        # Also allow assigning between compatible function types (e.g. worker parameter binding)
        return self.scope.is_assignable(rhs_t.scope)

    def propagate(self, rhs_t):
        lhs_t = self
        if lhs_t.name == rhs_t.name:
            if lhs_t.scope.is_object():
                lhs_t = rhs_t.clone(explicit=self.explicit)
            if not (lhs_t.explicit and not rhs_t.explicit) and lhs_t.scope.is_assignable(rhs_t.scope):
                param_types = tuple(t.clone(explicit=False) for t in rhs_t.param_types)
                lhs_t = lhs_t.clone(scope_name=rhs_t.scope_name, param_types=param_types, return_type=rhs_t.return_type.clone())
        return lhs_t
