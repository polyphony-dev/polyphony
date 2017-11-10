from collections import namedtuple
from .ir import CONST, RELOP, TEMP, MOVE, CJUMP, PHIBase
from .graph import Graph
from .block import CompositBlock
from logging import getLogger
logger = getLogger(__name__)

LoopInfo = namedtuple('LoopInfo', ('counter', 'init', 'update', 'cond', 'exit'))


class LoopNestTree(Graph):
    def set_root(self, n):
        self.add_node(n)
        self.root = n

    def traverse(self):
        return reversed(self.bfs_ordered_nodes())

    def is_child(self, loop_head1, loop_head2):
        return loop_head2 in self.succs(loop_head1)

    def is_leaf(self, loop_head):
        return not self.succs(loop_head)

    def get_children_of(self, loop_head):
        return self.succs(loop_head)

    def get_parent_of(self, loop_head):
        preds = self.preds(loop_head)
        assert len(preds) == 1
        return list(preds)[0]


class LoopDetector(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        scope.loop_nest_tree = LoopNestTree()

        ordered_blks = []
        visited = []
        head = scope.entry_block
        self._process_walk(head, ordered_blks, visited)
        assert head is ordered_blks[-1]

        lblks, blks = self._make_loop_block_bodies(ordered_blks)

        self._add_loop_tree_entry(head, lblks)
        scope.loop_nest_tree.set_root(head)

        LoopRegionSetter().process(scope)
        LoopInfoSetter().process(scope)
        LoopDependencyDetector().process(scope)

    def _make_loop_block(self, head, loop_region):
        lblks, blks = self._make_loop_block_bodies(loop_region)
        bodies = sorted(lblks + blks, key=lambda b: b.order)
        lb = CompositBlock(self.scope, head, bodies, [head] + loop_region)
        self._add_loop_tree_entry(lb, lblks)
        return lb

    def _make_loop_block_bodies(self, blks):
        sccs = self._extract_sccs(blks)
        lblks = []
        for scc in sccs:
            head = scc.pop()
            loop_region = scc

            # shrink blocks
            blks = [b for b in blks if b is not head and b not in loop_region]
            assert blks

            lb = self._make_loop_block(head, loop_region)
            lblks.append(lb)

            # re-connect
            for p in lb.preds:
                p.replace_succ(lb.head, lb)
                if isinstance(p, CompositBlock):
                    for r in p.region:
                        r.replace_succ(lb.head, lb)
            for s in lb.succs:
                s.replace_pred([lb.head] + lb.bodies, lb)

        return lblks, blks

    def _extract_sccs(self, ordered_blks):
        sccs = []
        for scc in self._find_scc(ordered_blks[:]):
            if len(scc) > 1:
                # we have to keep the depth-first-search order
                blks = [b for b in ordered_blks if b in scc]
                sccs.append(blks)
            elif len(scc) == 1 and scc[0] in scc[0].preds:
                blks = scc
                sccs.append(blks)
        return sccs

    # 'scc' is 'strongly connected components'
    def _find_scc(self, blks):
        sccs = []
        visited = []
        while blks:
            blk = blks[-1]
            scc = []
            self._process_back_walk(blk, blks, visited, scc)
            sccs.append(scc)
        return sccs

    def _process_walk(self, blk, blks, visited):
        visited.append(blk)
        if blk.succs:
            for succ in blk.succs:
                if succ not in visited:
                    self._process_walk(succ, blks, visited)
        blks.append(blk)

    def _process_back_walk(self, blk, blks, visited, scc):
        scc.append(blk)
        visited.append(blk)
        blks.remove(blk)
        for pred in blk.preds:
            if pred not in visited and pred in blks:
                self._process_back_walk(pred, blks, visited, scc)

    def _add_loop_tree_entry(self, parent, children):
        self.scope.loop_nest_tree.add_node(parent)
        for child in children:
            self.scope.loop_nest_tree.add_edge(parent, child)


class LoopInfoSetter(object):
    def process(self, scope):
        self.scope = scope
        for c in self.scope.loop_nest_tree.get_children_of(scope.entry_block):
            self._set_loop_info_rec(c)

    def _set_loop_info_rec(self, blk):
        if (blk.synth_params['scheduling'] == 'pipeline' or
                blk.synth_params['unroll']):
            self.set_loop_info(blk)
        for c in self.scope.loop_nest_tree.get_children_of(blk):
            self._set_loop_info_rec(c)

    def set_loop_info(self, loop_block):
        if loop_block.loop_info:
            return
        cjump = loop_block.head.stms[-1]
        if not cjump.is_a(CJUMP):
            # this loop may busy loop
            return
        cond_var = cjump.exp
        assert cond_var.is_a(TEMP)
        defs = self.scope.usedef.get_stms_defining(cond_var.symbol())
        assert len(defs) == 1
        cond_stm = list(defs)[0]
        assert cond_stm.is_a(MOVE)
        assert cond_stm.src.is_a(RELOP)
        loop_relexp = cond_stm.src

        if loop_relexp.left.is_a(TEMP) and loop_relexp.left.symbol().is_induction():
            assert loop_relexp.right.is_a([CONST, TEMP])
            loop_counter = loop_relexp.left.symbol()
        elif loop_relexp.right.is_a(TEMP) and loop_relexp.right.symbol().is_induction():
            assert loop_relexp.left.is_a([CONST, TEMP])
            loop_counter = loop_relexp.right.symbol()
        else:
            # this loop may busy loop
            return

        defs = self.scope.usedef.get_stms_defining(loop_counter)
        assert len(defs) == 1
        counter_def = list(defs)[0]
        counter_def.is_a(PHIBase)
        assert len(counter_def.args) == 2
        loop_init = counter_def.args[0]
        loop_update = counter_def.args[1]
        assert loop_update
        assert loop_init
        loop_exit = loop_block.succs[0]
        assert len(loop_block.succs) == 1
        loop_block.loop_info = LoopInfo(loop_counter, loop_init, loop_update, cond_var.symbol(), loop_exit)
        logger.debug(loop_block.loop_info)


class LoopRegionSetter(object):
    def process(self, scope):
        self.scope = scope
        children = self.scope.loop_nest_tree.get_children_of(scope.entry_block)
        for c in children:
            c.region = self._get_region(c)

    def _get_region(self, lb):
        assert isinstance(lb, CompositBlock)
        if self.scope.loop_nest_tree.is_leaf(lb):
            lb.region = [lb.head] + lb.bodies
        else:
            children = self.scope.loop_nest_tree.get_children_of(lb)
            lb.region = [lb.head] + [b for b in lb.bodies if not isinstance(b, CompositBlock)]
            for c in children:
                lb.region.extend(self._get_region(c))
        return lb.region


# hierarchize
class LoopDependencyDetector(object):
    def process(self, scope):
        all_blks = set([b for b in scope.traverse_blocks(full=False)])
        for lb in scope.loop_nest_tree.traverse():
            if lb is scope.loop_nest_tree.root:
                break
            outer_region = all_blks.difference(set(lb.region))
            inner_region = set(lb.region).difference(set([lb.head])).difference(set(lb.bodies))
            od, ou, id, iu = self._get_loop_block_dependency(scope.usedef,
                                                             lb,
                                                             outer_region,
                                                             inner_region)
            lb.outer_defs = od
            lb.outer_uses = ou
            lb.inner_defs = id
            lb.inner_uses = iu

    def _get_loop_block_dependency(self, usedef, lb, outer_region, inner_region):
        outer_defs = set()
        outer_uses = set()
        inner_defs = set()
        inner_uses = set()
        blocks = [lb.head] + [b for b in lb.bodies if not isinstance(b, CompositBlock)]
        usesyms = set()
        defsyms = set()
        for blk in blocks:
            usesyms |= usedef.get_syms_used_at(blk)
            defsyms |= usedef.get_syms_defined_at(blk)
        for sym in usesyms:
            defblks = usedef.get_blks_defining(sym)
            # Is this symbol used in the out of the loop?
            intersect = outer_region.intersection(defblks)
            if intersect:
                outer_defs.add(sym)
            intersect = inner_region.intersection(defblks)
            if intersect:
                inner_defs.add(sym)
        for sym in defsyms:
            useblks = usedef.get_blks_using(sym)
            # Is this symbol used in the out of the loop?
            intersect = outer_region.intersection(useblks)
            if intersect:
                outer_uses.add(sym)
            intersect = inner_region.intersection(useblks)
            if intersect:
                inner_uses.add(sym)

        return (outer_defs, outer_uses, inner_defs, inner_uses)
