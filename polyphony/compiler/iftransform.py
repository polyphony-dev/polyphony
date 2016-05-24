from .ir import CONST, CJUMP, MCJUMP
from logging import getLogger
logger = getLogger(__name__)

class IfTransformer:
    def process(self, scope):
        self._process(scope.blocks[0])

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

    def _process(self, block):
        if block.stms and block.stms[-1].is_a(CJUMP):
            cj = block.stms[-1]
            mj = MCJUMP()
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

        for succ in block.succs:
            if succ in block.succs_loop:
                continue
            self._process(succ)
