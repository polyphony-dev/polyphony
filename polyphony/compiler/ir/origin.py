from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .symbol import Symbol
    from .scope import Scope


class OriginRegistry:
    """Tracks clone/specialize origin relationships for Symbols and Scopes."""

    def __init__(self):
        self._sym_origins: dict[Symbol, Symbol] = {}
        self._scope_origins: dict[Scope, Scope] = {}

    def set_sym_origin(self, sym: Symbol, origin: Symbol):
        self._sym_origins[sym] = origin

    def sym_origin_of(self, sym: Symbol) -> Symbol | None:
        return self._sym_origins.get(sym)

    def root_sym(self, sym: Symbol, _visited: frozenset | None = None) -> Symbol:
        visited = _visited or frozenset()
        if sym in visited:
            raise ValueError(f'Circular origin chain detected for symbol {sym!r}')
        origin = self._sym_origins.get(sym)
        if origin:
            return self.root_sym(origin, visited | {sym})
        return sym

    def orig_name(self, sym: Symbol, _visited: frozenset | None = None) -> str:
        visited = _visited or frozenset()
        if sym in visited:
            raise ValueError(f'Circular origin chain detected for symbol {sym!r}')
        origin = self._sym_origins.get(sym)
        if origin:
            return self.orig_name(origin, visited | {sym})
        return sym.name

    def set_scope_origin(self, scope: Scope, origin: Scope):
        self._scope_origins[scope] = origin

    def scope_origin_of(self, scope: Scope) -> Scope | None:
        return self._scope_origins.get(scope)

    def clear(self):
        self._sym_origins.clear()
        self._scope_origins.clear()
