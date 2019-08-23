from collections import deque
from .env import env
from .graph import Graph
from .irvisitor import IRVisitor
from .scope import Scope


class CallGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        env.call_graph = Graph()
        self.call_graph = env.call_graph

    def process_all(self):
        g = Scope.global_scope()
        self.worklist = deque([g])
        visited = set()
        while self.worklist:
            scope = self.worklist.popleft()
            if scope in visited:
                continue
            visited.add(scope)
            self.process(scope)
        #print(self.call_graph)
        if not self.call_graph.succs(g):
            raise Warning(
                "Nothing is generated because any module or function didn't called in global scope.")
        called_scopes = set(self.call_graph.bfs_ordered_nodes())
        uncalled_scopes = set(env.scopes.values()).difference(called_scopes)
        return uncalled_scopes

    def process(self, scope):
        super().process(scope)

    def visit_CALL(self, ir):
        func_scope = ir.func_scope()
        assert func_scope
        self.call_graph.add_edge(self.scope, func_scope)
        self.worklist.append(func_scope)
        self.visit_args(ir.args, ir.kwargs)

    def visit_NEW(self, ir):
        assert ir.func_scope()
        ctor = ir.func_scope().find_ctor()
        assert ctor
        self.call_graph.add_edge(self.scope, ctor)
        self.worklist.append(ctor)

    def visit_TEMP(self, ir):
        if not ir.symbol().typ.is_function():
            return
        sym_scope = ir.symbol().typ.get_scope()
        if not sym_scope.is_worker():
            self.call_graph.add_edge(self.scope, sym_scope)
        self.worklist.append(sym_scope)

    def visit_ATTR(self, ir):
        if not ir.symbol().typ.is_function():
            return
        sym_scope = ir.symbol().typ.get_scope()
        if not sym_scope.is_worker():
            self.call_graph.add_edge(self.scope, sym_scope)
        self.worklist.append(sym_scope)


class DependencyGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        assert env.call_graph
        env.depend_graph = Graph()
        self.depend_graph = env.depend_graph

    def process_all(self):
        self.worklist = deque(env.call_graph.bfs_ordered_nodes())
        visited = set()
        while self.worklist:
            scope = self.worklist.popleft()
            if scope.is_method():
                self._add_dependency(scope, scope.parent)
            if scope.is_lib():
                continue
            if scope.is_directory():
                continue
            if scope in visited:
                continue
            visited.add(scope)
            self.process(scope)
        #print(self.depend_graph)
        using_scopes = set(self.depend_graph.bfs_ordered_nodes())
        unused_scopes = set(env.scopes.values()).difference(using_scopes)
        return using_scopes, unused_scopes

    def process(self, scope):
        self._add_dependency_for_params(scope)
        super().process(scope)

    def _add_dependency_for_params(self, scope):
        for p, _, _ in scope.params:
            if p.typ.is_object() or p.typ.is_function():
                param_scope = p.typ.get_scope()
                assert param_scope
                self._add_dependency(scope, param_scope)
                self.worklist.append(param_scope)

    def _add_dependency(self, user, used):
        if user is used:
            return
        if self.depend_graph.has_edge(user, used):
            return
        self.depend_graph.add_edge(user, used)

    def visit_TEMP(self, ir):
        if ir.sym.typ.has_scope():
            receiver_scope = ir.sym.typ.get_scope()
        elif ir.sym.scope is not self.scope:
            receiver_scope = ir.sym.ancestor.scope if ir.sym.ancestor else ir.sym.scope
        else:
            return
        assert receiver_scope
        self._add_dependency(self.scope, receiver_scope)
        self.worklist.append(receiver_scope)

    def visit_ATTR(self, ir):
        if ir.attr.typ.has_scope():
            attr_scope = ir.attr.typ.get_scope()
            assert attr_scope
            self._add_dependency(self.scope, attr_scope)
            self.worklist.append(attr_scope)
        # object referencing is also added
        self.visit(ir.exp)
        receiver = ir.tail()
        if not receiver.typ.has_scope():
            return
        receiver_scope = receiver.typ.get_scope()
        assert receiver_scope
        self._add_dependency(self.scope, receiver_scope)
        self.worklist.append(receiver_scope)

    def visit_NEW(self, ir):
        ctor = ir.sym.typ.get_scope().find_ctor()
        self._add_dependency(self.scope, ctor)
        self.visit_args(ir.args, ir.kwargs)
