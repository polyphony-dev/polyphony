from collections import deque
from ...common.env import env
from ...common.graph import Graph
from ..irvisitor import IRVisitor
from ..scope import Scope


class CallGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        env.call_graph = Graph()
        self.call_graph = env.call_graph

    def process_all(self):
        g = Scope.global_scope()
        # targets = [scope for scope, args in env.targets]
        self.worklist = deque([g])
        visited = set()
        while self.worklist:
            scope = self.worklist.popleft()
            if scope in visited:
                continue
            visited.add(scope)
            self.process(scope)
            if scope.is_class():
                self.worklist.append(scope.find_ctor())
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
        callee_scope = ir.callee_scope
        assert callee_scope
        self.call_graph.add_edge(self.scope, callee_scope)
        self.worklist.append(callee_scope)
        self.visit_args(ir.args, ir.kwargs)

    def visit_NEW(self, ir):
        callee_scope = ir.callee_scope
        assert callee_scope
        ctor = callee_scope.find_ctor()
        assert ctor
        self.call_graph.add_edge(self.scope, ctor)
        self.worklist.append(ctor)
        self.visit_args(ir.args, ir.kwargs)

    def visit_TEMP(self, ir):
        sym_t = ir.symbol.typ
        if not sym_t.is_function():
            return
        sym_scope = sym_t.scope
        if not sym_scope:
            return
        if not sym_scope.is_worker():
            self.call_graph.add_edge(self.scope, sym_scope)
        self.worklist.append(sym_scope)

    def visit_ATTR(self, ir):
        attr_t = ir.symbol.typ
        if not attr_t.is_function():
            return
        sym_scope = attr_t.scope
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
            p_t = p.typ
            if p_t.is_object() or p_t.is_function():
                param_scope = p_t.scope
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
        sym_t = ir.symbol.typ
        if sym_t.has_scope():
            receiver_scope = sym_t.scope
        elif ir.symbol.scope is not self.scope:
            receiver_scope = ir.symbol.ancestor.scope if ir.symbol.ancestor else ir.symbol.scope
        else:
            return
        assert receiver_scope
        self._add_dependency(self.scope, receiver_scope)
        self.worklist.append(receiver_scope)

    def visit_ATTR(self, ir):
        attr_t = ir.symbol.typ
        if attr_t.has_scope():
            attr_scope = attr_t.scope
            assert attr_scope
            self._add_dependency(self.scope, attr_scope)
            self.worklist.append(attr_scope)
        # object referencing is also added
        self.visit(ir.exp)
        receiver = ir.tail()
        receiver_t = receiver.typ
        if not receiver_t.has_scope():
            return
        receiver_scope = receiver_t.scope
        assert receiver_scope
        self._add_dependency(self.scope, receiver_scope)
        self.worklist.append(receiver_scope)

    def visit_NEW(self, ir):
        sym_t = ir.symbol.typ
        ctor = sym_t.scope.find_ctor()
        self._add_dependency(self.scope, ctor)
        self.visit_args(ir.args, ir.kwargs)
