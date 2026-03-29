"""Tests for polyphony.compiler.ir.loop (Region, Loop, LoopNestTree)."""
from pytests.compiler.base import make_block, MockScope
from polyphony.compiler.ir.loop import Region, Loop, LoopNestTree


class TestRegion:
    def _make_region(self):
        scope = MockScope('test')
        head = make_block(scope, 'head')
        b1 = make_block(scope, 'body1')
        b2 = make_block(scope, 'body2')
        inner1 = make_block(scope, 'inner1')
        inner2 = make_block(scope, 'inner2')
        region = Region(head, [b1, b2], [head, b1, b2, inner1, inner2])
        return region, head, b1, b2, inner1, inner2

    def test_init(self):
        region, head, b1, b2, inner1, inner2 = self._make_region()
        assert region.head is head
        assert region.bodies == [b1, b2]
        assert region.inner_blocks == [head, b1, b2, inner1, inner2]
        assert region.name == 'region' + str(head.num)

    def test_blocks(self):
        region, head, b1, b2, _, _ = self._make_region()
        blocks = region.blocks()
        assert blocks == [head, b1, b2]

    def test_str(self):
        region, head, b1, b2, inner1, inner2 = self._make_region()
        s = str(region)
        assert 'Region:' in s
        assert head.name in s
        assert b1.name in s
        assert b2.name in s
        assert inner1.name in s

    def test_append_body(self):
        region, head, b1, b2, inner1, inner2 = self._make_region()
        new_blk = make_block(MockScope('test'), 'new')
        region.append_body(new_blk)
        assert new_blk in region.bodies

    def test_append_inner(self):
        region, head, b1, b2, inner1, inner2 = self._make_region()
        new_blk = make_block(MockScope('test'), 'new')
        region.append_inner(new_blk)
        assert new_blk in region.inner_blocks

    def test_remove_body(self):
        region, head, b1, b2, inner1, inner2 = self._make_region()
        region.remove_body(b1)
        assert b1 not in region.bodies

    def test_remove_inner(self):
        region, head, b1, b2, inner1, inner2 = self._make_region()
        region.remove_inner(inner1)
        assert inner1 not in region.inner_blocks

    def test_usesyms_and_defsyms(self):
        """usesyms/defsyms delegate to usedef; test both with_inner_loop branches."""
        region, head, b1, b2, inner1, inner2 = self._make_region()

        class FakeUseDef:
            def __init__(self):
                self.used = {}
                self.defined = {}

            def get_syms_used_at(self, blk):
                return self.used.get(blk, set())

            def get_syms_defined_at(self, blk):
                return self.defined.get(blk, set())

        ud = FakeUseDef()
        ud.used[head] = {'x'}
        ud.used[b1] = {'y'}
        ud.used[inner1] = {'z'}
        ud.defined[head] = {'a'}
        ud.defined[b2] = {'b'}
        ud.defined[inner2] = {'c'}

        # with_inner_loop=True uses inner_blocks
        uses = region.usesyms(ud, with_inner_loop=True)
        assert 'x' in uses
        assert 'y' in uses
        assert 'z' in uses

        defs = region.defsyms(ud, with_inner_loop=True)
        assert 'a' in defs
        assert 'b' in defs
        assert 'c' in defs

        # with_inner_loop=False uses blocks() = [head] + bodies
        uses_no_inner = region.usesyms(ud, with_inner_loop=False)
        assert 'x' in uses_no_inner
        assert 'y' in uses_no_inner
        assert 'z' not in uses_no_inner

        defs_no_inner = region.defsyms(ud, with_inner_loop=False)
        assert 'a' in defs_no_inner
        assert 'b' in defs_no_inner
        assert 'c' not in defs_no_inner


class TestLoop:
    def _make_loop(self):
        scope = MockScope('test')
        head = make_block(scope, 'head')
        b1 = make_block(scope, 'body')
        inner1 = make_block(scope, 'inner')
        loop = Loop(head, [b1], [head, b1, inner1])
        return loop, head, b1, inner1

    def test_init(self):
        loop, head, b1, inner1 = self._make_loop()
        assert loop.head is head
        assert loop.bodies == [b1]
        assert loop.counter is None
        assert loop.init is None
        assert loop.update is None
        assert loop.cond is None
        assert loop.exits is None
        assert loop.outer_defs is None
        assert loop.outer_uses is None
        assert loop.inner_defs is None
        assert loop.inner_uses is None

    def test_str_minimal(self):
        loop, head, b1, _ = self._make_loop()
        s = str(loop)
        assert 'Loop:' in s
        assert head.name in s
        assert b1.name in s

    def test_str_full(self):
        loop, head, b1, inner1 = self._make_loop()
        exit_blk = make_block(MockScope('test'), 'exit')
        loop.exits = [exit_blk]
        loop.counter = 'i'
        loop.init = 'init_val'
        loop.update = 'update_val'
        loop.cond = 'cond_val'
        loop.outer_defs = {'od1', 'od2'}
        loop.outer_uses = {'ou1'}
        loop.inner_defs = {'id1'}
        loop.inner_uses = {'iu1', 'iu2'}
        s = str(loop)
        assert 'exits' in s
        assert 'counter' in s
        assert 'init' in s
        assert 'update' in s
        assert 'cond' in s
        assert 'outer_defs' in s
        assert 'outer_uses' in s
        assert 'inner_defs' in s
        assert 'inner_uses' in s


class TestLoopNestTree:
    def test_init(self):
        tree = LoopNestTree()
        assert tree.root is None

    def test_set_root(self):
        tree = LoopNestTree()
        tree.set_root('root')
        assert tree.root == 'root'
        assert tree.has_node('root')

    def test_traverse_forward_and_reverse(self):
        tree = LoopNestTree()
        tree.set_root('r')
        tree.add_edge('r', 'a')
        tree.add_edge('r', 'b')
        tree.add_edge('a', 'c')

        fwd = list(tree.traverse(reverse=False))
        rev = list(tree.traverse(reverse=True))
        assert fwd == list(reversed(rev))
        assert 'r' in fwd
        assert 'a' in fwd
        assert 'b' in fwd
        assert 'c' in fwd

    def test_is_child(self):
        tree = LoopNestTree()
        tree.set_root('r')
        tree.add_edge('r', 'a')
        tree.add_edge('r', 'b')
        assert tree.is_child('r', 'a')
        assert tree.is_child('r', 'b')
        assert not tree.is_child('a', 'b')

    def test_is_leaf(self):
        tree = LoopNestTree()
        tree.set_root('r')
        tree.add_edge('r', 'a')
        assert not tree.is_leaf('r')
        assert tree.is_leaf('a')

    def test_get_children_of(self):
        tree = LoopNestTree()
        tree.set_root('r')
        tree.add_edge('r', 'a')
        tree.add_edge('r', 'b')
        children = tree.get_children_of('r')
        assert 'a' in children
        assert 'b' in children

    def test_get_parent_of(self):
        tree = LoopNestTree()
        tree.set_root('r')
        tree.add_edge('r', 'a')
        assert tree.get_parent_of('a') == 'r'
        assert tree.get_parent_of('r') is None

    def test_len(self):
        tree = LoopNestTree()
        assert len(tree) == 0
        tree.set_root('r')
        assert len(tree) == 1
        tree.add_edge('r', 'a')
        assert len(tree) == 2
