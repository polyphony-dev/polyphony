from .env import env
from .graph import Graph
from .irvisitor import IRVisitor

class CallGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        if not env.call_graph:
            env.call_graph = Graph()
        self.call_graph = env.call_graph

    def visit_CALL(self, ir):
        assert ir.func_scope
        self.call_graph.add_edge(self.scope, ir.func_scope)
 
    def visit_NEW(self, ir):
        assert ir.func_scope
        ctor = ir.func_scope.find_ctor()
        assert ctor
        self.call_graph.add_edge(self.scope, ctor)

