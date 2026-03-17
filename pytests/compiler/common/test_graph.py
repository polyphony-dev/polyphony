"""Tests for polyphony.compiler.common.graph (SimpleOrderedSet and Graph)."""
import pytest
from polyphony.compiler.common.graph import SimpleOrderedSet, Graph, Edge


# ============================================================
# SimpleOrderedSet tests
# ============================================================

class TestSimpleOrderedSet:
    def test_empty(self):
        s = SimpleOrderedSet()
        assert len(s) == 0
        assert list(s) == []

    def test_init_with_items(self):
        s = SimpleOrderedSet([1, 2, 3])
        assert len(s) == 3
        assert list(s) == [1, 2, 3]

    def test_add(self):
        s = SimpleOrderedSet()
        s.add('a')
        s.add('b')
        assert len(s) == 2
        assert list(s) == ['a', 'b']

    def test_add_duplicate(self):
        s = SimpleOrderedSet()
        s.add('a')
        s.add('a')
        assert len(s) == 1
        assert list(s) == ['a']

    def test_contains(self):
        s = SimpleOrderedSet([10, 20])
        assert 10 in s
        assert 20 in s
        assert 30 not in s

    def test_discard(self):
        s = SimpleOrderedSet([1, 2, 3])
        s.discard(2)
        assert len(s) == 2
        assert list(s) == [1, 3]

    def test_discard_nonexistent(self):
        s = SimpleOrderedSet([1])
        s.discard(99)
        assert len(s) == 1

    def test_pop(self):
        s = SimpleOrderedSet([1, 2, 3])
        val = s.pop()
        assert val == 3
        assert len(s) == 2
        assert 3 not in s

    def test_pop_empty(self):
        s = SimpleOrderedSet()
        with pytest.raises(KeyError):
            s.pop()

    def test_iter(self):
        s = SimpleOrderedSet(['x', 'y', 'z'])
        assert list(s) == ['x', 'y', 'z']

    def test_reversed(self):
        s = SimpleOrderedSet([1, 2, 3])
        assert list(reversed(s)) == [3, 2, 1]

    def test_copy(self):
        # copy() uses copy.copy (shallow) so both share internal lists
        s = SimpleOrderedSet([1, 2])
        s2 = s.copy()
        # shallow copy means s2 is a different object
        assert s2 is not s
        # but internal state is shared (shallow copy behavior)
        assert len(s2) == 2

    def test_union(self):
        a = SimpleOrderedSet([1, 2])
        b = SimpleOrderedSet([3, 4])
        c = a.union(b)
        assert list(c) == [1, 2, 3, 4]

    def test_intersection(self):
        # intersection uses identity (is), so we need same objects
        obj1, obj2, obj3 = object(), object(), object()
        a = SimpleOrderedSet([obj1, obj2])
        b = SimpleOrderedSet([obj2, obj3])
        c = a.intersection(b)
        assert list(c) == [obj2]

    def test_intersection_empty(self):
        a = SimpleOrderedSet([1, 2])
        b = SimpleOrderedSet([3, 4])
        c = a.intersection(b)
        assert len(c) == 0

    def test_items(self):
        s = SimpleOrderedSet([1, 2, 3])
        items = s.items()
        assert items == {1, 2, 3}

    def test_orders(self):
        s = SimpleOrderedSet([3, 1, 2])
        assert s.orders() == [3, 1, 2]

    def test_repr_empty(self):
        s = SimpleOrderedSet()
        assert 'SimpleOrderedSet()' in repr(s)

    def test_repr_nonempty(self):
        s = SimpleOrderedSet([1, 2])
        r = repr(s)
        assert 'SimpleOrderedSet' in r
        assert '[1, 2]' in r

    def test_eq(self):
        a = SimpleOrderedSet([1, 2, 3])
        b = SimpleOrderedSet([1, 2, 3])
        assert a == b

    def test_neq_different_order(self):
        a = SimpleOrderedSet([1, 2])
        b = SimpleOrderedSet([2, 1])
        assert a != b

    def test_neq_different_type(self):
        a = SimpleOrderedSet([1])
        assert a != [1]


# ============================================================
# Graph tests
# ============================================================

class TestGraph:
    def test_empty(self):
        g = Graph()
        assert g.count() == 0
        assert g.get_nodes() == []

    def test_add_node(self):
        g = Graph()
        g.add_node('a')
        assert g.count() == 1
        assert g.has_node('a')
        assert not g.has_node('b')

    def test_add_edge(self):
        g = Graph()
        g.add_edge('a', 'b')
        assert g.has_node('a')
        assert g.has_node('b')
        assert g.has_edge('a', 'b')
        assert not g.has_edge('b', 'a')

    def test_del_node(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('b', 'c')
        g.del_node('b')
        assert not g.has_node('b')
        assert not g.has_edge('a', 'b')
        assert not g.has_edge('b', 'c')

    def test_del_edge(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('a', 'c')
        g.del_edge('a', 'b')
        assert not g.has_edge('a', 'b')
        assert g.has_edge('a', 'c')

    def test_del_edge_auto_del_node(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.del_edge('a', 'b')
        # both should be removed since they have no other edges
        assert not g.has_node('a')
        assert not g.has_node('b')

    def test_del_edge_no_auto_del(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.del_edge('a', 'b', auto_del_node=False)
        # nodes should remain
        assert g.has_node('a')
        assert g.has_node('b')

    def test_succs_preds(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('a', 'c')
        g.add_edge('b', 'c')
        assert 'b' in g.succs('a')
        assert 'c' in g.succs('a')
        assert 'a' in g.preds('b')
        assert 'a' in g.preds('c')
        assert 'b' in g.preds('c')

    def test_collect_sources(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('b', 'c')
        sources = g.collect_sources()
        assert sources == ['a']

    def test_collect_sinks(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('b', 'c')
        sinks = g.collect_sinks()
        assert sinks == ['c']

    def test_find_edge(self):
        g = Graph()
        g.add_edge('a', 'b', flags=42)
        e = g.find_edge('a', 'b')
        assert e is not None
        assert e.src == 'a'
        assert e.dst == 'b'
        assert e.flags == 42

    def test_find_edge_none(self):
        g = Graph()
        g.add_edge('a', 'b')
        assert g.find_edge('b', 'a') is None

    def test_str(self):
        g = Graph()
        g.add_edge('a', 'b')
        s = str(g)
        assert 'Nodes' in s
        assert 'Edges' in s

    def test_node_order_map(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('b', 'c')
        om = g.node_order_map()
        assert om['a'] < om['b']
        assert om['b'] < om['c']

    def test_node_order_map_cache(self):
        g = Graph()
        g.add_edge('a', 'b')
        om1 = g.node_order_map()
        om2 = g.node_order_map()
        assert om1 is om2  # cached

    def test_node_depth_map(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('a', 'c')
        g.add_edge('b', 'd')
        g.add_edge('c', 'd')
        dm = g.node_depth_map()
        assert dm['a'] == 0
        assert dm['b'] >= 1
        assert dm['c'] >= 1
        assert dm['d'] >= 2

    def test_node_depth_map_cache(self):
        g = Graph()
        g.add_edge('a', 'b')
        dm1 = g.node_depth_map()
        dm2 = g.node_depth_map()
        assert dm1 is dm2

    def test_bfs_ordered_nodes(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('b', 'c')
        nodes = g.bfs_ordered_nodes()
        assert nodes == ['a', 'b', 'c']

    def test_ordered_edges(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('b', 'c')
        edges = g.ordered_edges()
        assert len(edges) == 2
        assert edges[0].src == 'a'
        assert edges[1].src == 'b'

    def test_replace_succ(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.replace_succ('a', 'b', 'c')
        assert g.has_edge('a', 'c')
        assert not g.has_edge('a', 'b')

    def test_replace_pred(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.replace_pred('b', 'a', 'c')
        assert g.has_edge('c', 'b')
        assert not g.has_edge('a', 'b')

    def test_del_node_with_reconnect(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('b', 'c')
        g.del_node_with_reconnect('b')
        assert not g.has_node('b')
        assert g.has_edge('a', 'c')

    def test_add_edge_invalidates_cache(self):
        g = Graph()
        g.add_edge('a', 'b')
        _ = g.node_order_map()
        assert g.order_map_cache is not None
        g.add_edge('b', 'c')
        assert g.order_map_cache is None

    def test_del_edge_invalidates_cache(self):
        g = Graph()
        g.add_edge('a', 'b')
        g.add_edge('a', 'c')
        _ = g.node_order_map()
        g.del_edge('a', 'b', auto_del_node=False)
        assert g.order_map_cache is None
