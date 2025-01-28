
from dataclasses import dataclass, field
from .type import Type
from ...common.env import env


@dataclass(frozen=True)
class UndefinedType(Type):
    name: str = field(init=False, default='undef')

    def clone(self, **args):
        return self

    def can_assign(self, rhs_t):
        return True

    def propagate(self, rhs_t):
        return rhs_t.clone()
