from collections import defaultdict, namedtuple

Edge = namedtuple('Edge', ('src', 'dst', 'flags'))


class Graph(object):
    def __init__(self):
        self.succ_nodes = defaultdict(set)
        self.pred_nodes = defaultdict(set)
        self.edges = set()
        self.nodes = set()
        self.order_map_cache = None

    def __str__(self):
        s = ''
        for edge in self.ordered_edges():
            s += '{} --> {}: {}\n'.format(edge.src.__repr__(), edge.dst.__repr__(), edge.flags)
        return s

    def add_node(self, node):
        self.nodes.add(node)

    def del_node(self, node):
        self.nodes.remove(node)
        for edge in set(self.edges):
            if edge.src is node or edge.dst is node:
                self.edges.remove(edge)

    def has_node(self, node):
        return node in self.nodes

    def add_edge(self, src_node, dst_node, flags=0):
        self.add_node(src_node)
        self.add_node(dst_node)
        self.succ_nodes[src_node].add(dst_node)
        self.pred_nodes[dst_node].add(src_node)
        self.edges.add(Edge(src_node, dst_node, flags))
        self.order_map_cache = None

    def del_edge(self, src_node, dst_node):
        self.succ_nodes[src_node].remove(dst_node)
        self.pred_nodes[dst_node].remove(src_node)
        edge = self.find_edge(src_node, dst_node)
        assert edge
        self.edges.remove(edge)
        if not self.succs(src_node) and not self.preds(src_node):
            self.nodes.remove(src_node)
        if not self.succs(dst_node) and not self.preds(dst_node):
            self.nodes.remove(dst_node)
        self.order_map_cache = None

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

    def node_order_map(self):
        def set_order(pred, n, order, visited_edges):
            if (pred, n) in visited_edges:
                return
            visited_edges.add((pred, n))
            if order > order_map[n]:
                order_map[n] = order
            order += 1
            for succ in [succ for succ in self.succs(n)]:
                set_order(n, succ, order, visited_edges)

        if self.order_map_cache:
            return self.order_map_cache
        order_map = {}
        for n in self.nodes:
            order_map[n] = -1
        visited_edges = set()
        for source in self.collect_sources():
            set_order(None, source, 0, visited_edges)
        self.order_map_cache = order_map
        return order_map

    # bfs(breadth-first-search)
    def bfs_ordered_nodes(self):
        order_map = self.node_order_map()
        return sorted(self.nodes, key=lambda n: order_map[n])

    def ordered_edges(self):
        order_map = self.node_order_map()
        return sorted(self.edges, key=lambda e: (order_map[e.src], order_map[e.dst]))

    def is_dag(self):
        pass

    def replace_succ(self, node, old_succ, new_succ):
        self.del_edge(node, old_succ)
        self.add_edge(node, new_succ)

    def replace_pred(self, node, old_pred, new_pred):
        self.del_edge(old_pred, node)
        self.add_edge(new_pred, node)

    def find_succ_node_if(self, node, predicate):
        order_map = self.node_order_map()

        def find_succ_node_if_r(start_node, node, predicate, order_map):
            if order_map[node] < order_map[start_node]:
                return
            for succ in self.succs(node):
                if predicate(succ):
                    return succ
                else:
                    found = find_succ_node_if_r(start_node, succ, predicate, order_map)
                    if found:
                        return found
            return None
        return find_succ_node_if_r(node, node, predicate, order_map)
