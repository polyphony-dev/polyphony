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
        self.worklist = deque()
        visited = {g}
        self.process(g)
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
        using_scopes = set(self.call_graph.bfs_ordered_nodes())
        unused_scopes = set(env.scopes.values()).difference(using_scopes)
        return unused_scopes

    def _add_edge_for_params(self, scope):
        for p, _, _ in scope.params:
            if p.typ.is_object() or p.typ.is_function():
                param_scope = p.typ.get_scope()
                if scope.is_method() and param_scope is scope.parent:
                    continue
                self.call_graph.add_edge(scope, param_scope)

    def process(self, scope):
        self._add_edge_for_params(scope)
        super().process(scope)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        assert ir.func_scope
        self.call_graph.add_edge(self.scope, ir.func_scope)
        self.worklist.append(ir.func_scope)

        if ir.func_scope.orig_name == 'append_worker':
            _, w = ir.args[0]
            assert w.symbol().typ.is_function()
            assert w.symbol().typ.get_scope().is_worker()
            worker = w.symbol().typ.get_scope()
            self.call_graph.add_edge(self.scope, worker)
            self.worklist.append(worker)

    def visit_NEW(self, ir):
        assert ir.func_scope
        self.call_graph.add_edge(self.scope, ir.func_scope)
        self.worklist.append(ir.func_scope)

        ctor = ir.func_scope.find_ctor()
        self.call_graph.add_edge(ir.func_scope, ctor)
        self.worklist.append(ctor)

    def visit_ATTR(self, ir):
        # object referencing is also added as a callee
        self.visit(ir.exp)
        receiver = ir.tail()
        if not receiver.typ.has_scope():
            return
        receiver_scope = receiver.typ.get_scope()

        # for the sake of expedience of scope ordering
        # we don't add the edge which to its parent
        if receiver_scope is self.scope.parent:
            return
        if receiver_scope.is_lib():
            return
        if receiver_scope.is_class() and ir.symbol().typ.is_scalar():
            return
        self.call_graph.add_edge(self.scope, receiver_scope)
        self.worklist.append(receiver_scope)
