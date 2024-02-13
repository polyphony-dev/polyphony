from dataclasses import dataclass, field
from dataclasses import replace as dataclasses_replace
from .scopetype import ScopeType
from ...common.env import env


@dataclass(frozen=True)
class PortType(ScopeType):
    name: str = field(init=False, default='port')
    attrs: dict

    def clone(self, **args):
        attrs = self.attrs.copy()
        for k, v in args.items():
            attrs[k] = v
        return dataclasses_replace(self, attrs=attrs)

    @property
    def dtype(self):
        return self.attrs['dtype']

    @property
    def direction(self):
        return self.attrs['direction']

    @property
    def init(self):
        return self.attrs['init']

    @property
    def assigned(self):
        return self.attrs['assigned']

    @property
    def root_symbol(self):
        return self.attrs['root_symbol']

    def port_owner(self):
        if self.root_symbol.scope.is_ctor():
            return self.root_symbol.scope.parent
        else:
            return self.root_symbol.scope

    def __str__(self):
        if env.dev_debug_mode:
            if self.scope:
                return f'{self.name}<{self.scope.name}, {self.dtype}, {self.direction}>'
            else:
                return f'{self.name}<None>'
        return self.name

    def can_assign(self, rhs_t):
        if self.name != rhs_t.name:
            return False
        elif self.dtype != rhs_t.dtype:
            return False
        elif self.direction != rhs_t.direction:
            return False
        elif self.init != rhs_t.init:
            return False
        elif self.assigned != rhs_t.assigned:
            return False
        elif self.root_symbol != rhs_t.root_symbol:
            return False
        elif self.scope is not rhs_t.scope:
            return False
        return True

    def propagate(self, rhs_t):
        return self
