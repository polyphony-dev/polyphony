from .graph import Graph
from .ir import CONST, CJUMP, MCJUMP
from logging import getLogger
logger = getLogger(__name__)


class IfTransformer(object):
    def process(self, scope):
        self.mcjumps = []
        for blk in scope.traverse_blocks():
            self._process_block(blk)
        if self.mcjumps:
            self._sort_cfg_edges(scope)

    def _sort_cfg_edges(self, scope):
        g = Graph()
        for blk in scope.traverse_blocks():
            succs = [succ for succ in blk.succs if succ not in blk.succs_loop]
            for succ in succs:
                g.add_edge(blk, succ)

        dfs_order_map = g.node_order_map(is_breadth_first=False)
        for blk in scope.traverse_blocks():
            if len(blk.preds) > 1:
                blk.preds = sorted(blk.preds, key=lambda b: dfs_order_map[b])

    def _merge_else_cj(self, cj, mj):
        #has false block elif?
        if len(cj.false.stms) == 1 and cj.false.stms[0].is_a(CJUMP):
            else_cj = cj.false.stms[0]
            cj.false.succs = []
            cj.false.preds = []
            cj.false.stms = []

            mj.conds.append(else_cj.exp)
            mj.targets.append(else_cj.true)
            if not self._merge_else_cj(else_cj, mj):
                mj.conds.append(CONST(1))
                mj.targets.append(else_cj.false)
            return True
        return False

    def _process_block(self, block):
        if block.stms and block.stms[-1].is_a(CJUMP):
            cj = block.stms[-1]
            mj = MCJUMP()
            self.mcjumps.append(mj)
            mj.conds.append(cj.exp)
            mj.targets.append(cj.true)
            if self._merge_else_cj(cj, mj):
                block.stms.pop()
                mj.lineno = cj.lineno
                block.append_stm(mj)
                block.succs = []
                for target in mj.targets:
                    target.preds = [block]
                    block.succs.append(target)
                    logger.debug('target.block ' + target.name)
            logger.debug(mj)
