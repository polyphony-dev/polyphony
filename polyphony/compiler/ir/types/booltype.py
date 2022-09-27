from .simpletype import SimpleType
from ...common.env import env


class BoolType(SimpleType):
    def __init__(self, explicit):
        super().__init__('bool', env.scopes['__builtin__.bool'], explicit=explicit)

    def can_assign(self, rhs_t):
        return (self._name == rhs_t._name
            or rhs_t.is_int())
