from .scopetype import ScopeType
from ...common.env import env


class PortType(ScopeType):
    def __init__(self, scope, attrs, explicit=True):
        assert scope
        super().__init__('port', scope, explicit)
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
            if self._scope:
                return f'{self._name}<{self._scope.name}>'
            else:
                return f'{self._name}<None>'
        return self._name

    def __hash__(self):
        return hash((super().__hash__(), self.dtype, self.direction, self.init, self.assigned, self.root_symbol))

    def can_assign(self, rhs_t):
        if self._name != rhs_t._name:
            return False
        if self._scope is rhs_t._scope:
            return True
        elif rhs_t._scope and rhs_t._scope.is_subclassof(self._scope):
            return True
        return False

    def propagate(self, rhs_t):
        lhs_t = self
        if self._name == rhs_t._name:
            raise NotImplementedError()
            assert self._scope
            lhs_t = rhs_t.clone(explicit=self.explicit)
        return lhs_t
