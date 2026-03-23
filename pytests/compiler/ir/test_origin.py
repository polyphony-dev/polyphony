import pytest
from polyphony.compiler.ir.origin import OriginRegistry
from pytests.compiler.base import setup_test
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env


class TestOriginRegistrySymbol:
    def setup_method(self):
        setup_test()
        self.reg = OriginRegistry()

    def test_sym_origin_none(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        sym = scope.add_sym('x', set(), Type.int())
        assert self.reg.sym_origin_of(sym) is None

    def test_set_and_get_sym_origin(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        orig = scope.add_sym('x', set(), Type.int())
        clone = scope.add_sym('x_1', set(), Type.int())
        self.reg.set_sym_origin(clone, orig)
        assert self.reg.sym_origin_of(clone) is orig

    def test_root_sym(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        s1 = scope.add_sym('x', set(), Type.int())
        s2 = scope.add_sym('x_1', set(), Type.int())
        s3 = scope.add_sym('x_2', set(), Type.int())
        self.reg.set_sym_origin(s2, s1)
        self.reg.set_sym_origin(s3, s2)
        assert self.reg.root_sym(s3) is s1
        assert self.reg.root_sym(s1) is s1

    def test_orig_name(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        s1 = scope.add_sym('x', set(), Type.int())
        s2 = scope.add_sym('x_specialized', set(), Type.int())
        self.reg.set_sym_origin(s2, s1)
        assert self.reg.orig_name(s2) == 'x'
        assert self.reg.orig_name(s1) == 'x'

    def test_root_sym_cycle_raises(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        s1 = scope.add_sym('a', set(), Type.int())
        s2 = scope.add_sym('b', set(), Type.int())
        self.reg.set_sym_origin(s1, s2)
        self.reg.set_sym_origin(s2, s1)  # cycle: s1 -> s2 -> s1
        with pytest.raises(ValueError, match='Circular origin chain'):
            self.reg.root_sym(s1)

    def test_orig_name_cycle_raises(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        s1 = scope.add_sym('a', set(), Type.int())
        self.reg.set_sym_origin(s1, s1)  # self-loop
        with pytest.raises(ValueError, match='Circular origin chain'):
            self.reg.orig_name(s1)


class TestOriginRegistryScope:
    def setup_method(self):
        setup_test()
        self.reg = OriginRegistry()

    def test_scope_origin_none(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        assert self.reg.scope_origin_of(scope) is None

    def test_set_and_get_scope_origin(self):
        top = env.scopes[env.global_scope_name]
        orig = Scope.create(top, 'C', {'class'}, 1)
        clone = Scope.create(top, 'C_int', {'class'}, 1)
        self.reg.set_scope_origin(clone, orig)
        assert self.reg.scope_origin_of(clone) is orig

    def test_clear(self):
        top = env.scopes[env.global_scope_name]
        scope = Scope.create(top, 'f', {'function'}, 1)
        sym = scope.add_sym('x', set(), Type.int())
        self.reg.set_sym_origin(sym, sym)
        self.reg.set_scope_origin(scope, scope)
        self.reg.clear()
        assert self.reg.sym_origin_of(sym) is None
        assert self.reg.scope_origin_of(scope) is None
