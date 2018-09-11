from .graph import Graph
from .ir import *
from .type import Type
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
                c = CONST(1)
                c.lineno = cj.lineno
                mj.conds.append(c)
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


class IfCondTransformer(object):
    def process(self, scope):
        self.scope = scope
        for blk in scope.traverse_blocks():
            self._process_block(blk)

    def _process_block(self, block):
        if block.stms and block.stms[-1].is_a(MCJUMP):
            # if-elif-else conditions are converted as follows
            #
            # if p0:   ...
            # elif p1: ...
            # elif p2: ...
            # else:    ...
            #
            # if p0:   ...
            # if !p0 and p1: ...
            # if !p0 and !p1 and p2: ...
            # if !p0 and !p1 and !p2: ...
            mj = block.stms[-1]
            for c in mj.conds:
                assert c.is_a(TEMP) or c.is_a(CONST)
            prevs = []
            new_cond_exps = []
            for c in mj.conds:
                new_c = None
                for prev_c in prevs:
                    if new_c:
                        new_c = RELOP('And', new_c, UNOP('Not', prev_c))
                    else:
                        new_c = UNOP('Not', prev_c)
                    new_c.lineno = c.lineno
                if new_c:
                    if c.is_a(CONST):
                        assert c.value == 1
                        pass
                    else:
                        new_c = RELOP('And', new_c, c)
                    new_c.lineno = c.lineno
                else:
                    new_c = c
                new_cond_exps.append(new_c)
                prevs.append(c)
            # simplify condtion expressions
            new_conds = []
            for c in new_cond_exps:
                if c.is_a(TEMP):
                    new_conds.append(c)
                else:
                    new_sym = self.scope.add_condition_sym()
                    new_sym.typ = Type.bool_t
                    new_c = TEMP(new_sym, Ctx.STORE)
                    new_c.lineno = c.lineno
                    mv = MOVE(new_c, c)
                    mv.lineno = c.lineno
                    block.insert_stm(-1, mv)
                    new_c = TEMP(new_sym, Ctx.LOAD)
                    new_c.lineno = c.lineno
                    new_conds.append(new_c)
            mj.conds = new_conds
