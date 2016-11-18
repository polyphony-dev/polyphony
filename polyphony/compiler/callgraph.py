from collections import defaultdict, namedtuple
from .env import env
from .ir import *
from .irvisitor import IRVisitor
from .symbol import function_name
from .utils import replace_item

Edge = namedtuple('Edge', ('src', 'dst', 'flags'))

class Graph:
    def __init__(self):
        self.succ_nodes = defaultdict(set)
        self.pred_nodes = defaultdict(set)
        self.edges = set()
        self.nodes = set()

    def add_node(self, node):
        self.nodes.add(node)

    def add_edge(self, src_node, dst_node, flags = 0):
        self.succ_nodes[src_node].add(dst_node)
        self.pred_nodes[dst_node].add(src_node)
        self.edges.add(Edge(src_node, dst_node, flags))

    def del_edge(self, src_node, dst_node):
        self.succ_nodes[src_node].remove(dst_node)
        self.pred_nodes[dst_node].remove(src_node)
        edge = self.find_edge(src_node, dst_node)
        assert edge
        self.edges.remove(edge)

    def find_edge(self, src_node, dst_node):
        for edge in self.edges:
            if edge.src is src_node and edge.dst is dst_node:
                return edge
        return None

    def succs(self, node):
        return self.succ_nodes[node]

    def preds(self, node):
        return self.pred_nodes[node]

    def collect_sources(self):
        return [n for n in self.nodes if not self.preds(n)]

    def collect_sinks(self):
        return [n for n in self.nodes if not self.succs(n)]

    # bfs(breadth-first-search)
    def bfs_orderd_nodes(self):
        def set_order(n, order):
            if order > order_map[n]:
                order_map[n] = order
            order += 1
            for succ in [succ for succ in self.succs(n)]:
                set_order(succ, order)

        order_map = {}
        for n in self.nodes:
            order_map[n] = -1
        for source in self.collect_sources():
            set_order(source, 0)
        return sorted(self.nodes, key=lambda n: order_map[n])

    def is_dag(self):
        pass

    def replace_succ(self, node, old_succ, new_succ):
        self.del_edge(node, old_succ)
        self.add_edge(node, new_succ)

    def replace_pred(self, node, old_pred, new_ored):
        self.del_edge(old_pred, node)
        self.add_edge(new_pred, node)


class CallGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        env.callgraph = Graph()

    def visit_CALL(self, ir):
        #super().visit(ir)
        
        if ir.func.is_a(TEMP):
            func_name = function_name(ir.func.sym)
            func_scope = self.scope.find_scope(func_name)
            self.scope.add_callee_scope(func_scope)
        elif ir.func.is_a(ATTR):
            func_name = ir.func.attr
            
        #    args = list(map(self.visit, node.args))
        #    return CALL(func, args, None)
        
class AttributeScopeDetector(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_ATTR(self, ir):
        super().visit(ir)

        if ir.exp.is_a(TEMP):
            exptyp = ir.exp.sym.typ
        elif ir.exp.is_a(ATTR):
            pass
        if Type.is_object(exptyp) or Type.is_class(exptyp):
            scope = Type.extra(exptyp)
            assert isinstance(scope, Scope)
            ir.scope = scope

