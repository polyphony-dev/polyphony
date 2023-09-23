from .scopetype import ScopeType
from ...common.env import env


class PortType(ScopeType):
    def __init__(self, scope_name, attrs, explicit=True):
        super().__init__('port', scope_name, explicit)
        self._dtype = attrs['dtype']
        self._direction = attrs['direction']
        self._init = attrs['init']
        self._assigned = attrs['assigned']
        self._root_symbol = attrs['root_symbol']

    @property
    def dtype(self):
        return self._dtype

    @property
    def direction(self):
        return self._direction

    @property
    def init(self):
        return self._init

    @property
    def assigned(self):
        return self._assigned

    @property
    def root_symbol(self):
        return self._root_symbol

    def port_owner(self):
        if self.root_symbol.scope.is_ctor():
            return self.root_symbol.scope.parent
        else:
            return self.root_symbol.scope

    def __str__(self):
        if env.dev_debug_mode:
            if self.scope:
                return f'{self._name}<{self.scope.base_name}, {self.dtype}, {self.direction}>'
            else:
                return f'{self._name}<None>'
        return self._name

    def __hash__(self):
        return hash((super().__hash__(), self.dtype, self.direction, self.init, self.assigned, self.root_symbol))

    def can_assign(self, rhs_t):
        if self._name != rhs_t._name:
            return False
        elif self._dtype != rhs_t._dtype:
            return False
        elif self._direction != rhs_t._direction:
            return False
        elif self._init != rhs_t._init:
            return False
        elif self._assigned != rhs_t._assigned:
            return False
        elif self._root_symbol != rhs_t._root_symbol:
            return False
        elif self._scope is not rhs_t._scope:
            return False
        return True

    def propagate(self, rhs_t):
        return self
