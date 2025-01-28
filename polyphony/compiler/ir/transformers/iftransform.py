from ..ir import *
from ..types.type import Type
from ...common.graph import Graph
from logging import getLogger
logger = getLogger(__name__)


class IfTransformer(object):
    def process(self, scope):
        for blk in scope.traverse_blocks():
            self._process_block(blk)

    def _merge_else_cj(self, cj, conds, targets):
        if len(cj.false.stms) == 1 and cj.false.stms[0].is_a(CJUMP):
            else_cj = cj.false.stms[0]
            cj.false.succs = []
            cj.false.preds = []
            cj.false.stms = []

            conds.append(else_cj.exp)
            targets.append(else_cj.true)
            if not self._merge_else_cj(else_cj, conds, targets):
                conds.append(CONST(1))
                targets.append(else_cj.false)
            return True
        return False

    def _process_block(self, block):
        if block.stms and block.stms[-1].is_a(CJUMP):
            conds = []
            targets = []
            cj = block.stms[-1]
            conds.append(cj.exp)
            targets.append(cj.true)
            if self._merge_else_cj(cj, conds, targets):
                block.stms.pop()
                mj = MCJUMP(conds, targets, cj.loc)
                block.append_stm(mj)
                block.succs = []
                for target in targets:
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
                if new_c:
                    if c.is_a(CONST):
                        assert c.value == 1
                        pass
                    else:
                        new_c = RELOP('And', new_c, c)
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
                    new_sym.typ = Type.bool()
                    mv = MOVE(TEMP(new_sym.name), c)
                    block.insert_stm(-1, mv)
                    new_conds.append(TEMP(new_sym.name))
            mj.conds = new_conds
