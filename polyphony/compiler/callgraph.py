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
        def is_special_scope(s):
            return s.is_global() or s.is_class() or s.is_testbench()

        for s in Scope.get_scopes(contain_global=True, contain_class=True):
            self.process(s)

        using_scopes = set(self.call_graph.bfs_ordered_nodes())
        unused_scopes = set(env.scopes.values()).difference(using_scopes)
        unused_scopes = [s for s in unused_scopes if not is_special_scope(s)]
        return unused_scopes

    def visit_CALL(self, ir):
        assert ir.func_scope
        self.call_graph.add_edge(self.scope, ir.func_scope)
 
    def visit_NEW(self, ir):
        assert ir.func_scope
        ctor = ir.func_scope.find_ctor()
        assert ctor
        self.call_graph.add_edge(self.scope, ctor)

