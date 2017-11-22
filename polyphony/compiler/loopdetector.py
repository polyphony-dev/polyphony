from .ir import CONST, RELOP, TEMP, MOVE, CJUMP, PHIBase, LPHI
from .loop import Region, Loop
from logging import getLogger
logger = getLogger(__name__)


class LoopDetector(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.scope.reset_loop_tree()
        ordered_blks = []
        visited = []
        head = scope.entry_block
        self._process_walk(head, ordered_blks, visited)
        assert head is ordered_blks[-1]

        regions, bodies = self._make_loop_bodies(ordered_blks)
        bodies.remove(head)
        top_region = Region(head, bodies, ordered_blks)
        self.scope.append_child_regions(top_region, regions)
        scope.set_top_region(top_region)

    def _make_loop_region(self, head, loop_inner_blks):
        regions, bodies = self._make_loop_bodies(loop_inner_blks)
        loop = Loop(head, bodies, [head] + loop_inner_blks)
        self.scope.append_child_regions(loop, regions)
        return loop

    def _make_loop_bodies(self, blks):
        sccs = self._extract_sccs(blks)
        regions = []
        for scc in sccs:
            head = scc.pop()
            loop_inner_blks = scc

            # shrink blocks
            blks = [b for b in blks if b is not head and b not in loop_inner_blks]
            assert blks

            r = self._make_loop_region(head, loop_inner_blks)
            regions.append(r)
        blks = sorted(blks, key=lambda b: b.order)
        return regions, blks

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


class LoopInfoSetter(object):
    def process(self, scope):
        self.scope = scope
        for loop in self.scope.child_regions(self.scope.top_region()):
            self._set_loop_info_rec(loop)

    def _set_loop_info_rec(self, loop):
        self.set_loop_info(loop)
        for child in self.scope.child_regions(loop):
            self._set_loop_info_rec(child)

    def set_loop_info(self, loop):
        assert isinstance(loop, Loop)
        if loop.counter:
            return
        cjump = loop.head.stms[-1]
        if not cjump.is_a(CJUMP):
            # this loop may busy loop
            return
        cond_var = cjump.exp
        loop.cond = cond_var.symbol()
        assert cond_var.is_a(TEMP)
        defs = self.scope.usedef.get_stms_defining(cond_var.symbol())
        assert len(defs) == 1
        cond_stm = list(defs)[0]
        assert cond_stm.is_a(MOVE)
        if not cond_stm.src.is_a(RELOP):
            return
        loop_relexp = cond_stm.src

        if loop_relexp.left.is_a(TEMP) and loop_relexp.left.symbol().is_induction():
            assert loop_relexp.right.is_a([CONST, TEMP])
            loop.counter = loop_relexp.left.symbol()
            loop.counter.add_tag('loop_counter')
        elif loop_relexp.right.is_a(TEMP) and loop_relexp.right.symbol().is_induction():
            assert loop_relexp.left.is_a([CONST, TEMP])
            loop.counter = loop_relexp.right.symbol()
            loop.counter.add_tag('loop_counter')
        else:
            lphis = loop.head.collect_stms(LPHI)
            for lphi in lphis:
                if lphi.var.symbol().is_loop_counter():
                    loop.counter = lphi.var.symbol()
                    break
            else:
                # this loop may busy loop
                return
        defs = self.scope.usedef.get_stms_defining(loop.counter)
        assert len(defs) == 1
        counter_def = list(defs)[0]
        counter_def.is_a(PHIBase)
        assert len(counter_def.args) == 2
        loop.init = counter_def.args[0]
        loop.update = counter_def.args[1]
        loop.exits = []
        for blk in loop.inner_blocks:
            for s in blk.succs:
                if s not in loop.inner_blocks:
                    loop.exits.append(s)
        assert loop.update
        assert loop.init
        logger.debug(loop)


class LoopRegionSetter(object):
    def process(self, scope):
        self.scope = scope
        top = self.scope.top_region()
        children = self.scope.child_regions(top)
        for c in children:
            c.inner_blocks = self._get_region_blks(c)
        top.inner_blocks = list(self.scope.traverse_blocks())

    def _get_region_blks(self, loop):
        assert isinstance(loop, Loop)
        if self.scope.is_leaf_region(loop):
            loop.inner_blocks = loop.blocks()
        else:
            loop.inner_blocks = loop.blocks()
            children = self.scope.child_regions(loop)
            for c in children:
                loop.inner_blocks.extend(self._get_region_blks(c))
        return loop.inner_blocks


# hierarchize
class LoopDependencyDetector(object):
    def process(self, scope):
        all_blks = set([b for b in scope.traverse_blocks()])
        for loop in scope.traverse_regions(reverse=True):
            if loop is scope.top_region():
                break
            outer_region = all_blks.difference(set(loop.inner_blocks))
            inner_region = set(loop.inner_blocks) - (set(loop.blocks()))
            od, ou, id, iu = self._get_loop_block_dependency(scope.usedef,
                                                             loop,
                                                             outer_region,
                                                             inner_region)
            loop.outer_defs = od
            loop.outer_uses = ou
            loop.inner_defs = id
            loop.inner_uses = iu

    def _get_loop_block_dependency(self, usedef, loop, outer_region, inner_region):
        outer_defs = set()
        outer_uses = set()
        inner_defs = set()
        inner_uses = set()
        blocks = loop.blocks()
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
