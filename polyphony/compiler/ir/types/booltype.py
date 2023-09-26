from dataclasses import dataclass, field
from .simpletype import SimpleType
from ...common.env import env

@dataclass(frozen=True)
class BoolType(SimpleType):
    name: str = field(init=False, default='bool')
    scope_name: str = field(init=False, default='__builtin__.bool')

    def can_assign(self, rhs_t):
        return (self.name == rhs_t.name
            or rhs_t.is_int())

    @property
    def width(self):
        return 1

    @property
    def signed(self):
        return False
