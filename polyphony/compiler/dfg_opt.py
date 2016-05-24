from .ir import TEMP, MOVE, MSTORE
from logging import getLogger
logger = getLogger(__name__)

class DFGOptimizer:
    def process(self, scope):
        self.scope = scope
        for dfg in self.scope.dfgs():
            self._process(scope, dfg)

    def _process(self, scope, dfg):
        return

        for n in dfg.nodes:
            if not n.is_stm():
                continue
            if not n.tag.is_a(MOVE):
                continue
            if not n.tag.src.is_a(TEMP):
                continue
            preds = dfg.preds_typ(n, 'DefUse')
            if len(preds) == 1:
                defstm = preds[0].tag
                copystm = n.tag
                if defstm.is_a(MOVE) and defstm.src.is_a(MSTORE):
                    continue

                eliminated = copystm.src
                using_stms = scope.usedef.get_use_stms_by_sym(eliminated.sym)
                if len(using_stms) != 1:
                    continue
                if copystm.dst.sym.is_return():
                    continue
                logger.debug('!!! can eliminate ' + str(preds[0]))
                logger.debug('     ' + str(n))
                logger.debug([str(stm) for stm in using_stms])

                defstm.dst = copystm.dst
                copystm.block.stms.remove(copystm)
                dfg.remove_edge(preds[0], n)
                dfg.remove_node(n)
