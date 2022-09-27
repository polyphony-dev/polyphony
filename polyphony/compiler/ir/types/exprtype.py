from .type import Type
from ...common.env import env


class ExprType(Type):
    def __init__(self, expr):
        super().__init__('expr', explicit=True)
        assert expr
        self._expr = expr

    @property
    def expr(self):
        return self._expr

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        clone._expr = self.expr.clone()
        for k, v in args.items():
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
        return clone

    def can_assign(self, rhs_t):
        return self._name == rhs_t._name and self._expr == rhs_t._expr

    def propagate(self, rhs_t):
        return self

    def __str__(self):
        if env.dev_debug_mode:
            return f'expr<{self._expr}>'
        return self._name

    def __hash__(self):
        return hash((super().__hash__(), hash(self._expr)))

    def __eq__(self, other):
        return self._name == other._name and self._expr == other._expr
