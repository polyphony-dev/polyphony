from collections import defaultdict, namedtuple
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
        self.is_dag_cache = None

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
        node.g = self
        self.nodes.add(node)

    def del_node(self, node):
        self.nodes.discard(node)
        for edge in set(self.edges):
            if edge.src is node or edge.dst is node:
                self.del_edge(edge.src, edge.dst, auto_del_node=False)

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
        self.is_dag_cache = None

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
        self.is_dag_cache = None

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

    def node_order_map(self, is_breadth_first):
        def set_order(pred, n, bf_order, df_order, visited_edges):
            if (pred, n) in visited_edges:
                return df_order
            visited_edges.add((pred, n))
            if bf_order > bf_order_map[n]:
                bf_order_map[n] = bf_order
            if df_order > df_order_map[n]:
                df_order_map[n] = df_order
            bf_order += 1
            df_order += 1
            for succ in self.succs(n):
                df_order = set_order(n, succ, bf_order, df_order, visited_edges)
            return df_order
        if self.order_map_cache:
            if is_breadth_first:
                return self.order_map_cache[0]
            else:
                return self.order_map_cache[1]
        bf_order_map = {}
        df_order_map = {}
        for n in self.nodes:
            bf_order_map[n] = -1
            df_order_map[n] = -1
        visited_edges = set()
        for source in self.collect_sources():
            set_order(None, source, 0, 0, visited_edges)
        self.order_map_cache = bf_order_map, df_order_map
        if is_breadth_first:
            return bf_order_map
        else:
            return df_order_map

    # bfs(breadth-first-search)
    def bfs_ordered_nodes(self):
        order_map = self.node_order_map(is_breadth_first=True)
        return sorted(self.nodes, key=lambda n: order_map[n])

    def dfs_ordered_nodes(self):
        order_map = self.node_order_map(is_breadth_first=False)
        return sorted(self.nodes, key=lambda n: order_map[n])

    def ordered_edges(self, is_breadth_first=True):
        order_map = self.node_order_map(is_breadth_first)
        return sorted(self.edges, key=lambda e: (order_map[e.src], order_map[e.dst]))

    def is_dag(self):
        if not self.is_dag_cache:
            self.is_dag_cache = False if self.extract_sccs() else True
        return self.is_dag_cache

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

    def extract_sccs(self):
        '''
        Extract Strongly Connected Components
        '''
        nodes = self.dfs_ordered_nodes()
        return self._extract_sccs(list(reversed(nodes)))

    def _extract_sccs(self, ordered_nodes):
        sccs = []
        for scc in self._find_scc(ordered_nodes[:]):
            if len(scc) > 1:
                # we have to keep the depth-first-search order
                nodes = [n for n in ordered_nodes if n in scc]
                sccs.append(nodes)
            elif len(scc) == 1 and scc[0] in self.preds(scc[0]):
                nodes = scc
                sccs.append(nodes)
        return sccs

    def _find_scc(self, nodes):
        sccs = []
        visited = []
        while nodes:
            node = nodes[-1]
            scc = []
            self._find_scc_back_walk(node, nodes, visited, scc)
            sccs.append(scc)
        return sccs

    def _find_scc_back_walk(self, node, nodes, visited, scc):
        scc.append(node)
        visited.append(node)
        nodes.remove(node)
        for pred in self.preds(node):
            if pred not in visited and pred in nodes:
                self._find_scc_back_walk(pred, nodes, visited, scc)


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
