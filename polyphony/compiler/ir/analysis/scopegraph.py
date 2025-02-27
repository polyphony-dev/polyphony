from collections import deque
from ...common.graph import Graph
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..scope import Scope
from ..symbol import Symbol
from logging import getLogger
logger = getLogger(__name__)


class ScopeDependencyGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()

    def process_scopes(self, scopes):
        self.depend_graph = Graph()

        self.worklist = deque(scopes)
        self.visited = set()
        while self.worklist:
            scope = self.worklist.popleft()
            self.depend_graph.add_node(scope)
            if scope in self.visited:
                continue
            self.visited.add(scope)
            self.scope = scope
            self.process(scope)
        return self.visited

    def _add_dependency(self, user, used):
        if user is used:
            return
        if self.depend_graph.has_edge(user, used):
            return
        self.depend_graph.add_edge(user, used)

    def _add_scope(self, scope):
        assert scope
        if not self.scope.is_descendants_of(scope):
            self._add_dependency(self.scope, scope)
        if scope.is_containable():
            for child in scope.children:
                self._add_dependency(scope, child)
        if scope.is_lib():
            return
        if scope.is_directory():
            return
        if scope in self.visited:
            return
        self.worklist.append(scope)

    def visit_TEMP(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym_t = sym.typ
        if sym_t.has_scope():
            if sym.is_self():
                return
            if sym_t.has_scope():
                self._add_scope(sym_t.scope)
        else:
            # If self.scope refers an external symbol with a value type, the scope of the symbol is added
            if sym.scope is not self.scope:
                self._add_scope(sym.scope)

    def visit_ATTR(self, ir):
        self.visit(ir.exp)

    def visit_NEW(self, ir):
        qsyms = qualified_symbols(ir, self.scope)
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        sym_t = sym.typ
        self._add_scope(sym_t.scope)
        self.visit_args(ir.args, ir.kwargs)


class UsingScopeDetector(IRVisitor):
    def __init__(self):
        super().__init__()

    def process_scopes(self, scopes):
        self.depend_graph = Graph()

        self.worklist = deque(scopes)
        self.visited = set()
        while self.worklist:
            scope = self.worklist.popleft()
            if scope in self.visited:
                continue
            self.visited.add(scope)
            if scope.is_class():
                scopes = self._collect_scope_symbol(scope)
                for s in scopes:
                    self._add_scope(s)
            self.scope = scope
            self.process(scope)
        return self.visited

    def _add_dependency(self, user, used):
        if user is used:
            return
        if self.depend_graph.has_edge(user, used):
            return
        self.depend_graph.add_edge(user, used)

    def _collect_scope_symbol(self, scope):
        scopes = []
        for sym in scope.symbols.values():
            if sym.typ.has_scope():
                s = sym.typ.scope
                scopes.append(s)
        return scopes

    def _add_scope(self, scope):
        assert scope
        self._add_dependency(self.scope, scope)
        if scope in self.visited:
            return
        if Scope.is_normal_scope(scope) and scope not in self.worklist:
            self.worklist.append(scope)

    def visit_TEMP(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym_t = sym.typ
        if sym_t.has_scope():
            if sym.is_self():
                return
            if sym_t.has_scope():
                self._add_scope(sym_t.scope)
        else:
            # If self.scope refers an external symbol with a value type, the scope of the symbol is added
            if sym.scope is not self.scope:
                self._add_scope(sym.scope)

    def visit_ATTR(self, ir):
        self.visit(ir.exp)
        qsyms = qualified_symbols(ir, self.scope)
        symbol = qsyms[-1]
        if isinstance(symbol, str):
            return
        attr_t = symbol.typ
        if attr_t.has_scope():
            attr_scope = attr_t.scope
            self._add_scope(attr_scope)

    def visit_NEW(self, ir):
        qsyms = qualified_symbols(ir, self.scope)
        symbol = qsyms[-1]
        assert isinstance(symbol, Symbol)
        sym_t = symbol.typ
        if sym_t.has_scope():
            self._add_scope(sym_t.scope)
            self._add_scope(sym_t.scope.find_ctor())
        self.visit_args(ir.args, ir.kwargs)
