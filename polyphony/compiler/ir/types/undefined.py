from .type import Type
from ...common.env import env


class UndefinedType(Type):
    def __init__(self):
        super().__init__('undef', explicit=False)

    def clone(self, **args):
        return self

    def can_assign(self, rhs_t):
        return True

    def propagate(self, rhs_t):
        return rhs_t.clone()
