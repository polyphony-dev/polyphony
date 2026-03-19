from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader as IrParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.dominator import (
    DominatorTree, DominatorTreeBuilder, DominanceFrontierBuilder,
)
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    parser = IrParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def blk_by_name(scope, suffix):
    """Find a block whose nametag matches the suffix."""
    for blk in scope.traverse_blocks():
        if blk.nametag == suffix:
            return blk
    raise ValueError(f'Block {suffix} not found')


# --- DominatorTree unit tests ---

def test_tree_basic():
    """Manual tree construction and query."""
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    a = Block(scope, nametag='a')
    b = Block(scope, nametag='b')
    c = Block(scope, nametag='c')

    tree = DominatorTree()
    tree.add_node(a)
    tree.add_node(b)
    tree.add_node(c)
    tree.add_edge(a, b)
    tree.add_edge(a, c)

    assert tree.get_parent_of(b) is a
    assert tree.get_parent_of(c) is a
    assert tree.get_parent_of(a) is None
    assert set(tree.get_children_of(a)) == {b, c}
    assert tree.get_children_of(b) == []
    assert tree.is_child(a, b)
    assert not tree.is_child(b, a)


def test_tree_is_dominator():
    """a dominates b, b dominates c => a dominates c."""
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    a = Block(scope, nametag='a')
    b = Block(scope, nametag='b')
    c = Block(scope, nametag='c')

    tree = DominatorTree()
    tree.add_node(a)
    tree.add_node(b)
    tree.add_node(c)
    tree.add_edge(a, b)
    tree.add_edge(b, c)

    # a dominates c (transitively through b)
    assert tree.is_dominator(a, c)
    assert tree.is_dominator(a, b)
    assert tree.is_dominator(b, c)
    # c does not dominate a
    assert not tree.is_dominator(c, a)
    # every node dominates itself
    assert tree.is_dominator(a, a)


# --- DominatorTreeBuilder tests ---

def test_linear_cfg():
    """Linear CFG: blk1 -> blk2 -> blk3. Each block dominated by all predecessors."""
    setup_test()
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv x 2
j blk3

blk3:
mv x 3
'''
    scope = build_scope(src)
    tree = DominatorTreeBuilder(scope).process()

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')
    blk3 = blk_by_name(scope, 'blk3')

    # blk1 dominates blk2, blk2 dominates blk3
    assert tree.get_parent_of(blk2) is blk1
    assert tree.get_parent_of(blk3) is blk2
    assert tree.get_parent_of(blk1) is None


def test_diamond_cfg():
    """Diamond CFG:
         blk1
        /    \\
      blk2  blk3
        \\    /
         exit
    blk1 dominates all. exit's immediate dominator is blk1.
    """
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
j exit

blk3:
mv x 2
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    tree = DominatorTreeBuilder(scope).process()

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')
    blk3 = blk_by_name(scope, 'blk3')
    exit_blk = blk_by_name(scope, 'exit')

    assert tree.get_parent_of(blk2) is blk1
    assert tree.get_parent_of(blk3) is blk1
    # exit is dominated by blk1 (not blk2 or blk3, since both paths merge)
    assert tree.get_parent_of(exit_blk) is blk1
    assert tree.get_parent_of(blk1) is None


def test_sequential_branch_cfg():
    """
      blk1 -> blk2 -> blk3 -> exit
                 \\             /
                  blk4 -------
    blk2 dominates blk3 and blk4. exit's idom is blk2.
    """
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv x 0
j blk2

blk2:
mv c True
cj c blk3 blk4

blk3:
mv x 1
j exit

blk4:
mv x 2
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    tree = DominatorTreeBuilder(scope).process()

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')
    blk3 = blk_by_name(scope, 'blk3')
    blk4 = blk_by_name(scope, 'blk4')
    exit_blk = blk_by_name(scope, 'exit')

    assert tree.get_parent_of(blk2) is blk1
    assert tree.get_parent_of(blk3) is blk2
    assert tree.get_parent_of(blk4) is blk2
    assert tree.get_parent_of(exit_blk) is blk2


def test_single_block():
    """Single block scope. No edges in dominator tree."""
    setup_test()
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)
    tree = DominatorTreeBuilder(scope).process()

    blk1 = blk_by_name(scope, 'blk1')
    assert tree.get_parent_of(blk1) is None
    assert tree.get_children_of(blk1) == []


# --- DominanceFrontierBuilder tests ---

def test_frontier_diamond():
    """Diamond CFG: DF[blk2] = {exit}, DF[blk3] = {exit}, DF[blk1] = {}."""
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
j exit

blk3:
mv x 2
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    tree = DominatorTreeBuilder(scope).process()

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')
    blk3 = blk_by_name(scope, 'blk3')
    exit_blk = blk_by_name(scope, 'exit')

    df = DominanceFrontierBuilder().process(blk1, tree)

    assert df[blk1] == set()
    assert df[blk2] == {exit_blk}
    assert df[blk3] == {exit_blk}
    assert df[exit_blk] == set()


def test_frontier_linear():
    """Linear CFG: all dominance frontiers are empty."""
    setup_test()
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv x 2
j blk3

blk3:
mv x 3
'''
    scope = build_scope(src)
    tree = DominatorTreeBuilder(scope).process()
    blk1 = blk_by_name(scope, 'blk1')

    df = DominanceFrontierBuilder().process(blk1, tree)

    for blk, frontier in df.items():
        assert frontier == set(), f'{blk.nametag} has non-empty frontier'
