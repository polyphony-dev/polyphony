from logging import getLogger
logger = getLogger(__name__)


class DominatorTree(object):
    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_node(self, n):
        if n not in self.nodes:
            self.nodes.append(n)

    def add_edge(self, n1, n2):
        edge = (n1, n2)
        if edge not in self.edges:
            self.edges.append(edge)

    def get_parent_of(self, n):
        '''parent is immidiate dominator'''
        for n1, n2 in self.edges:
            if n2 is n:
                return n1
        return None

    def get_children_of(self, n):
        return [n2 for n1, n2 in self.edges if n1 is n]

    #is v dominator of n?
    def is_dominator(self, n, v):
        if n is v:
            return True
        for c in self.get_children_of(n):
            if self.is_dominator(c, v):
                return True
        return False

    def is_child(self, n1, n2):
        for _n1, _n2 in self.edges:
            if _n1 is n1 and _n2 is n2:
                return True
        return False

    def dump(self):
        logger.debug('dominator tree')
        logger.debug(str(self))

    def __str__(self):
        s = ''
        for n1, n2 in sorted(self.edges, key=lambda n: n[0].name):
            s += '{} --> {}\n'.format(n1.name, n2.name)
        return s


class DominatorTreeBuilder(object):
    def __init__(self, scope):
        self.scope = scope
        self.dominators = {}

    def process(self):
        first_block = self.scope.entry_block
        self._fwd_blks = self._succs
        self._fwd_loop_blks = self._succs_loop
        self._back_blks = self._preds
        self._back_loop_blks = self._preds_loop

        self.all_blocks = [blk for blk in self.scope.traverse_blocks()]
        #collect dominators for each block
        self._walk_block(first_block, self._visit_Block_find_dominator)

        #build dominator tree
        tree = DominatorTree()
        for b, doms in self.dominators.items():
            for dom in doms:
                assert dom.order >= 0
            domlist = sorted(list(doms))
            assert b is domlist[-1]
            if len(domlist) >= 2:
                d1 = domlist[-2]  # immediate dominator
                d2 = domlist[-1]  # block itself
                tree.add_node(d1)
                tree.add_node(d2)
                tree.add_edge(d1, d2)
        return tree

    def _succs(self, blk):
        succs = []
        for s in blk.succs:
            succs.append(s)
        return succs

    def _succs_loop(self, blk):
        return blk.succs_loop

    def _preds(self, blk):
        preds = []
        for s in blk.preds:
            preds.append(s)
        return preds

    def _preds_loop(self, blk):
        return blk.preds_loop

    def _walk_block(self, block, visit_func):
        visited = set()
        stack = [block]
        while stack:
            blk = stack.pop()
            visit_func(blk)
            visited.add(blk)
            succs = self._fwd_blks(blk)
            for succ in reversed(succs):
                if (succ in self._fwd_loop_blks(blk) or
                        succ in visited or
                        succ in stack):
                    continue
                stack.append(succ)

    def _visit_Block_find_dominator(self, block):
        if block in self.dominators:
            return self.dominators[block]

        preds = self._back_blks(block)
        if preds:
            doms = set(self.all_blocks)
            for p in preds:
                if p in self._back_loop_blks(block):
                    continue
                ds = self._visit_Block_find_dominator(p)
                doms = ds.intersection(doms)
            doms.add(block)
        else:
            #It must be the super-src block
            doms = set([block])
        self.dominators[block] = doms
        return doms


class DominanceFrontierBuilder(object):
    def __init__(self):
        self.dominance_frontier = {}

    def process(self, block, tree):
        self._compute_df(block, tree)
        return self.dominance_frontier

    def _compute_df(self, block, tree):
        '''DF[n] = DFlocal[n] | [DFup[c] for c in tree.children[n]]

        DFlocal[n]: The successors of n that are not strictly dominated by n;
        DFup[n]: Nodes in the dominance frontier of n
        that are not strictly dominated by n's immediate dominator.
        '''
        result = set()
        for succ in block.succs:
            if tree.get_parent_of(succ) is not block:
                result.add(succ)
        for c in tree.get_children_of(block):
            self._compute_df(c, tree)
            for v in self.dominance_frontier[c]:
                if not tree.is_dominator(block, v) or block is v:
                    result.add(v)

        self.dominance_frontier[block] = result
