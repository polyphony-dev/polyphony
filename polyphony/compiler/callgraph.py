from .env import env
from .graph import Graph
from .irvisitor import IRVisitor
from .scope import Scope


class CallGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        if not env.call_graph:
            env.call_graph = Graph()
        self.call_graph = env.call_graph

    def process_all(self):
        for s in Scope.get_scopes(with_global=True, with_class=True):
            for p, _, _ in s.params:
                if p.typ.is_object():
                    param_scope = p.typ.get_scope()
                    if s.is_method() and param_scope is s.parent:
                        continue
                    self.call_graph.add_edge(s, param_scope)
            self.process(s)

        using_scopes = set(self.call_graph.bfs_ordered_nodes())
        unused_scopes = set(env.scopes.values()).difference(using_scopes)
        return unused_scopes

    def visit_CALL(self, ir):
        self.visit(ir.func)
        assert ir.func_scope
        self.call_graph.add_edge(self.scope, ir.func_scope)

    def visit_NEW(self, ir):
        assert ir.func_scope
        self.call_graph.add_edge(self.scope, ir.func_scope)
        ctor = ir.func_scope.find_ctor()
        self.call_graph.add_edge(ir.func_scope, ctor)

    def visit_ATTR(self, ir):
        # object referencing is also added as a callee
        self.visit(ir.exp)
        receiver = ir.tail()
        if not receiver.typ.is_object():
            return
        receiver_scope = receiver.typ.get_scope()

        # for the sake of expedience of scope ordering
        # we don't add the edge which to its parent
        if receiver_scope is self.scope.parent:
            return
        self.call_graph.add_edge(self.scope, receiver_scope)
