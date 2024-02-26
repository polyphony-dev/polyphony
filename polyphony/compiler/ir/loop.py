from __future__ import annotations
from ..common.graph import Graph
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .symbol import Symbol
    from .block import Block
    from .ir import IRExp


class Region(object):
    def __init__(self, head: Block, bodies: list[Block], inner_blocks: list[Block]):
        self.head = head
        self.bodies = bodies
        self.inner_blocks = inner_blocks
        self.name = 'region' + str(head.num)

    def blocks(self):
        return [self.head] + self.bodies

    def __str__(self):
        s = 'Region: {}\n'.format(self.name)
        s += ' # head: {}\n'.format(self.head.name)
        s += ' # bodies: {'
        s += ', '.join([blk.name for blk in self.bodies])
        s += '}\n'
        s += ' # inner_blocks: {'
        s += ', '.join([blk.name for blk in self.inner_blocks])
        s += '}\n'
        return s

    def usesyms(self, usedef, with_inner_loop=True):
        if with_inner_loop:
            blocks = self.inner_blocks
        else:
            blocks = self.blocks()
        usesyms = set()
        for blk in blocks:
            usesyms |= usedef.get_syms_used_at(blk)
        return usesyms

    def defsyms(self, usedef, with_inner_loop=True):
        if with_inner_loop:
            blocks = self.inner_blocks
        else:
            blocks = self.blocks()
        defsyms = set()
        for blk in blocks:
            defsyms |= usedef.get_syms_defined_at(blk)
        return defsyms

    def append_body(self, blk):
        assert blk not in self.bodies
        self.bodies.append(blk)

    def append_inner(self, blk):
        assert blk not in self.inner_blocks
        self.inner_blocks.append(blk)

    def remove_body(self, blk):
        assert blk in self.bodies
        self.bodies.remove(blk)

    def remove_inner(self, blk):
        assert blk in self.inner_blocks
        self.inner_blocks.remove(blk)


class Loop(Region):
    def __init__(self, head, bodies, region):
        super().__init__(head, bodies, region)
        self.counter: Symbol = None
        self.init: IRExp = None
        self.update: IRExp = None
        self.cond: Symbol = None
        self.exits: list[Block] = None
        self.outer_defs: set[Symbol] = None
        self.outer_uses: set[Symbol] = None
        self.inner_defs: set[Symbol] = None
        self.inner_uses: set[Symbol] = None

    def __str__(self):
        s = 'Loop: {}\n'.format(self.name)
        s += ' # head: {}\n'.format(self.head.name)
        s += ' # bodies: {'
        s += ', '.join([blk.name for blk in self.bodies])
        s += '}\n'
        if self.exits:
            s += ' # exits: {'
            s += ', '.join([blk.name for blk in self.exits])
            s += '}\n'
        if self.counter:
            s += ' # counter: {}\n'.format(self.counter)
        if self.init:
            s += ' # init: {}\n'.format(self.init)
        if self.update:
            s += ' # update: {}\n'.format(self.update)
        if self.cond:
            s += ' # cond: {}\n'.format(self.cond)
        if self.outer_defs:
            s += ' # outer_defs: {'
            s += ', '.join([str(d) for d in self.outer_defs])
            s += '}\n'
        if self.outer_uses:
            s += ' # outer_uses: {'
            s += ', '.join([str(u) for u in self.outer_uses])
            s += '}\n'
        if self.inner_defs:
            s += ' # inner_defs: {'
            s += ', '.join([str(d) for d in self.inner_defs])
            s += '}\n'
        if self.inner_uses:
            s += ' # inner_uses: {'
            s += ', '.join([str(u) for u in self.inner_uses])
            s += '}\n'
        return s


class LoopNestTree(Graph):
    def __init__(self):
        super().__init__()
        self.root = None

    def set_root(self, n):
        self.add_node(n)
        self.root = n

    def traverse(self, reverse=False):
        if reverse:
            return reversed(self.bfs_ordered_nodes())
        else:
            return self.bfs_ordered_nodes()

    def is_child(self, loop1, loop2):
        return loop2 in self.succs(loop1)

    def is_leaf(self, loop):
        return not self.succs(loop)

    def get_children_of(self, loop):
        return self.succs(loop)

    def get_parent_of(self, loop):
        preds = self.preds(loop)
        if not preds:
            return None
        assert len(preds) == 1
        return list(preds)[0]

    def __len__(self):
        return self.count()
