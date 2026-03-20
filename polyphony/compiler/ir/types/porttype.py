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
        val = self.attrs['root_symbol']
        if isinstance(val, str):
            # Lazy resolution: "scope_name:sym_name"
            scope_name, sym_name = val.rsplit(':', 1)
            return env.scopes[scope_name].find_sym(sym_name)
        return val

    def port_owner(self):
        root_sym = self.root_symbol
        assert root_sym is not None
        if root_sym.scope.is_ctor():
            return root_sym.scope.parent
        else:
            return root_sym.scope

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
