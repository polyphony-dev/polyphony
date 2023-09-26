
from dataclasses import dataclass
from dataclasses import replace as dataclasses_replace
from .type import Type
from ...common.env import env
from ..scope import Scope

@dataclass(frozen=True)
class SimpleType(Type):
    scope_name: str

    def __init__(self, name: str, scope_name: str, explicit=True):
        super().__init__(name, explicit)
        object.__setattr__(self, "scope_name", scope_name)

    @property
    def scope(self) -> Scope:
        assert self.scope_name in env.scopes
        return env.scopes[self.scope_name]

    def clone(self, **args):
        return dataclasses_replace(self, **args)

    def can_assign(self, rhs_t) -> bool:
        return self.name == rhs_t.name

    def propagate(self, rhs_t) -> Type:
        if self.name == rhs_t.name and rhs_t.explicit:
            return rhs_t.clone(explicit=self.explicit)
        return self
