from dataclasses import dataclass, field
from .scopetype import ScopeType


@dataclass(frozen=True)
class ClassType(ScopeType):
    name: str = field(init=False, default='class')

    def __post_init__(self):
        assert self.scope.is_class() or self.scope.is_typeclass()

    def can_assign(self, rhs_t):
        return self.name == rhs_t.name and (self.scope is rhs_t.scope or self.scope.is_object())

    def propagate(self, rhs_t):
        if self.name == rhs_t.name and self.scope.is_object():
            return rhs_t.clone(explicit=self.explicit)
        else:
            return self
