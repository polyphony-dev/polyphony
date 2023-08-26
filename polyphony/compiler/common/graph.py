from collections import defaultdict, namedtuple, deque
import copy


class SimpleOrderedSet(object):
    def __init__(self, items=None):
        if items is None:
            items = []
        self.__items = set(items)
        self.__orders = list(items)

    def __len__(self):
        return len(self.__items)

    def __contains__(self, key):
        return key in self.__items

    def copy(self):
        return copy.copy(self)

    def add(self, key):
        if key not in self.__items:
            self.__items.add(key)
            self.__orders.append(key)

    def discard(self, key):
        if key in self.__items:
            self.__items.discard(key)
            self.__orders.remove(key)

    def __iter__(self):
        return iter(self.__orders)

    def __reversed__(self):
        return reversed(self.__orders)

    def pop(self, last=True):
        if not self.__items:
            raise KeyError('set is empty')
        key = self.__orders.pop()
        self.__items.discard(key)
        return key

    def union(self, other):
        return SimpleOrderedSet(self.__orders + other.orders())

    def intersection(self, other):
        items = []
        for item0 in self.__orders:
            for item1 in other.orders():
                if item0 is item1:
                    items.append(item0)
                    break
        return SimpleOrderedSet(items)

    def items(self):
        return self.__items.copy()

    def orders(self):
        return self.__orders.copy()

    def __repr__(self):
        if not self:
            return '{}()'.format(self.__class__.__name__,)
        return '{}({})'.format(self.__class__.__name__, self.__orders)

    def __eq__(self, other):
        return isinstance(other, SimpleOrderedSet) and self.__orders == other.__orders


Edge = namedtuple('Edge', ('src', 'dst', 'flags'))


class Graph(object):
    def __init__(self):
        self.succ_nodes = defaultdict(SimpleOrderedSet)
        self.pred_nodes = defaultdict(SimpleOrderedSet)
        self.edges = SimpleOrderedSet()
        self.nodes = SimpleOrderedSet()
        self.order_map_cache = None
        self.depth_map_cache = None

    def __str__(self):
        s = 'Nodes\n'
        for node in self.get_nodes():
            s += '{}\n'.format(node.__repr__())
        s += 'Edges\n'
        for edge in self.ordered_edges():
            s += '{} --> {}: {}\n'.format(edge.src.__repr__(), edge.dst.__repr__(), edge.flags)
        return s

    def count(self):
        return len(self.nodes)

    def add_node(self, node):
        # node.g = self
        self.nodes.add(node)

    def del_node(self, node):
        self.nodes.discard(node)
        for edge in set(self.edges):
            if edge.src is node or edge.dst is node:
                self.del_edge(edge.src, edge.dst, auto_del_node=False)

    def del_node_with_reconnect(self, node):
        succs = self.succs(node)
        preds = self.preds(node)
        for s in succs:
            for p in preds:
                self.add_edge(p, s)
        self.del_node(node)

    def has_node(self, node):
        return node in self.nodes

    def get_nodes(self):
        return self.nodes.orders()

    def add_edge(self, src_node, dst_node, flags=0):
        self.add_node(src_node)
        self.add_node(dst_node)
        self.succ_nodes[src_node].add(dst_node)
        self.pred_nodes[dst_node].add(src_node)
        self.edges.add(Edge(src_node, dst_node, flags))
        self.order_map_cache = None

    def has_edge(self, src_node, dst_node, flags=0):
        return Edge(src_node, dst_node, flags) in self.edges

    def del_edge(self, src_node, dst_node, auto_del_node=True):
        self.succ_nodes[src_node].discard(dst_node)
        self.pred_nodes[dst_node].discard(src_node)
        edge = self.find_edge(src_node, dst_node)
        assert edge
        self.edges.discard(edge)
        if auto_del_node:
            if not self.succs(src_node) and not self.preds(src_node):
                self.nodes.discard(src_node)
            if not self.succs(dst_node) and not self.preds(dst_node):
                self.nodes.discard(dst_node)
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

    def node_depth_map(self):
        if self.depth_map_cache:
            return self.depth_map_cache
        visited_nodes = set()
        depth_map = {}
        for n in self.nodes:
            depth_map[n] = -1
        for source in self.collect_sources():
            depth_map[source] = 0
        node_q = deque()
        node_q.append(self.collect_sources())
        depth = 0
        while node_q:
            nodes = node_q.popleft()
            for node in nodes:
                if node in visited_nodes:
                    if depth_map[node] < depth:
                        depth_map[node] = depth
                    continue
                depth_map[node] = depth
                visited_nodes.add(node)
                node_q.append(self.succs(node))
            depth += 1
        self.depth_map_cache = depth_map
        return depth_map

    def node_order_map(self):
        if self.order_map_cache:
            return self.order_map_cache
        visited_nodes = set()
        order_map = {}
        for n in self.nodes:
            order_map[n] = -1
        node_q = deque(self.collect_sources())
        order = 0
        while node_q:
            node = node_q.popleft()
            if node in visited_nodes:
                continue
            order_map[node] = order
            visited_nodes.add(node)
            node_q.extend(self.succs(node))
            order += 1
        self.order_map_cache = order_map
        return order_map

    # bfs(breadth-first-search)
    def bfs_ordered_nodes(self):
        order_map = self.node_order_map()
        return sorted(self.nodes, key=lambda n: order_map[n])

    def ordered_edges(self):
        order_map = self.node_order_map()
        return sorted(self.edges, key=lambda e: (order_map[e.src], order_map[e.dst]))

    def replace_succ(self, node, old_succ, new_succ):
        self.del_edge(node, old_succ)
        self.add_edge(node, new_succ)

    def replace_pred(self, node, old_pred, new_pred):
        self.del_edge(old_pred, node)
        self.add_edge(new_pred, node)

    def write_dot(self, name):
        from .env import env
        try:
            import pydot
        except ImportError:
            raise
        # force disable debug mode to simplify the caption
        debug_mode = env.dev_debug_mode
        env.dev_debug_mode = False

        g = pydot.Dot(name, graph_type='digraph')
        node_map = {node: pydot.Node(str(node.name), shape='box') for node in self.get_nodes()}
        for n in node_map.values():
            g.add_node(n)

        for node in node_map.keys():
            from_node = node_map[node]
            for succ in self.succs(node):
                to_node = node_map[succ]
                g.add_edge(pydot.Edge(from_node, to_node))
        g.write_png('{}/{}.png'.format(env.debug_output_dir, name))
        env.dev_debug_mode = debug_mode


def test_graph():
    a = 'a'
    b = 'b'
    c = 'c'
    d = 'd'
    e = 'e'
    f = 'f'

    g = Graph()

    g.add_edge(a, b)
    g.add_edge(b, c)
    g.add_edge(b, d)
    g.add_edge(c, e)
    #g.add_edge(c, f)
    g.add_edge(e, f)
    g.add_edge(f, c)

    print(g)
    sccs = g.extract_sccs()
    print(sccs)


if __name__ == '__main__':
    test_graph()
