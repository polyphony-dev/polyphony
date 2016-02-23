from collections import defaultdict
from .ir import RELOP, CONST, TEMP, CJUMP, MOVE, PHI
from .symbol import Symbol
from .dominator import DominatorTreeBuilder
from .varreplacer import VarReplacer
from .type import Type
from logging import getLogger
logger = getLogger(__name__)


class PHICondResolver:
    def __init__(self):
        self.count = 0

    def process(self, scope):
        self.scope = scope

        self._collect_phi()
        phis = self.phis[:]
        for phi in phis:
            self._divide_phi_to_mv(phi)

    def _collect_phi(self):
        self.phis = []
        for b in self.scope.blocks:
            for stm in b.stms:
                if isinstance(stm, PHI):
                    #if stm.var.sym.is_memory():
                    #    continue
                    self.phis.append(stm)

    def _divide_phi_to_mv(self, phi):
        usedef = self.scope.usedef
        args = []
        conds = []
        for i, (arg, blk) in enumerate(phi.args):
            pred = blk
            mv = MOVE(TEMP(phi.var.sym, 'Store'), arg)
            #TODO: track the lineno
            mv.lineno = 1
            pred.stms.insert(-1, mv)
            mv.block = pred
            logger.debug('PHI divide into ' + str(mv))
            #update usedef table
            if isinstance(arg, TEMP):
                usedef.remove_var_use(arg, phi)
                usedef.add_var_use(mv.src, mv)
            elif isinstance(arg, CONST):
                usedef.remove_const_use(arg, phi)
                usedef.add_const_use(mv.src, mv)

            usedef.add_var_def(mv.dst, mv)

        usedef.remove_var_def(phi.var, phi)
        phi.block.stms.remove(phi)
        self.phis.remove(phi)

        #assert len(usedef.get_sym_defs_stm(phi.var.sym)) == len(phi.argv())
