from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING
from ..common.common import Tagged
from ..common.env import env
from logging import getLogger
from .types.type import Type
logger = getLogger(__name__)
if TYPE_CHECKING:
    from .scope import Scope


class Symbol(Tagged):
    __slots__ = ['_id', '_name', '_scope', '_typ']
    id_counter = 0

    TAGS = {
        'temp', 'param', 'return', 'condition', 'induction', 'alias', 'free',
        'self', 'static', 'subobject', 'field',
        'builtin', 'inlined', 'flattened', 'pipelined', 'predefined',
        'loop_counter', 'register', 'inherited', 'imported',
        'unresolved_scope',
        'typevar',
    }

    @classmethod
    def initialize(cls):
        cls.id_counter = 0

    @classmethod
    def unique_name(cls, prefix: str=''):
        if not prefix:
            prefix = cls.temp_prefix
        return '{}{}'.format(prefix, cls.id_counter)

    return_name = '@return'
    condition_prefix = '@c'
    temp_prefix = '@t'
    param_prefix = '@in'

    def __init__(self, name: str, scope: 'Scope', tags: set[str], typ: Type|None=None):
        super().__init__(tags)
        if not typ:
            typ = Type.none()
        self._id = Symbol.id_counter
        self._name = name
        self._scope = scope
        self._typ = typ
        Symbol.id_counter += 1

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str):
        # assert False
        self._name = name

    @property
    def scope(self) -> Scope:
        return self._scope

    @property
    def typ(self) -> Type:
        return self._typ

    @typ.setter
    def typ(self, typ):
        if self._typ == typ:
            return
        self._typ = typ

    def __str__(self):
        if self.is_unresolved_scope():
            return f'?{self._name}'
        return self._name

    def __repr__(self):
        return f'{self._name}({self._id}, {self.scope.name})'

    def __lt__(self, other):
        return self._name < other._name

    def orig_name(self):
        return env.origin_registry.orig_name(self)

    def root_sym(self) -> 'Symbol':
        return env.origin_registry.root_sym(self)

    def hdl_name(self):
        if self._typ.is_port():
            name = self._name[:]
        elif self._typ.is_object() and self._typ.scope.is_module():
            ancestor = env.origin_registry.sym_origin_of(self)
            if ancestor:
                return ancestor.hdl_name()
            name = self._name[:]
        elif self._name[0] == '@' or self._name[0] == '!':
            name = self._name[1:]
        else:
            name = self._name[:]
        name = name.replace('#', '')
        return name

    def clone(self, scope, new_name):
        assert new_name
        newsym = Symbol(new_name,
                        scope,
                        set(self.tags),
                        self._typ)
        origin = env.origin_registry.sym_origin_of(self)
        if origin:
            env.origin_registry.set_sym_origin(newsym, origin)
        return newsym
