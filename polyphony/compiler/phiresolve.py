from collections import defaultdict
from .ir import *
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
        for b in self.scope.traverse_blocks():
            for stm in b.stms:
                if stm.is_a(PHI):
                    #if stm.var.sym.is_memory():
                    #    continue
                    self.phis.append(stm)

    def _divide_phi_to_mv(self, phi):
        usedef = self.scope.usedef
        args = []
        conds = []
        for i, (arg, blk) in enumerate(zip(phi.args, phi.defblks)):
            if not blk:
                continue
            pred = blk
            mv = MOVE(phi.var.clone(), arg)
            mv.lineno = arg.lineno
            mv.dst.lineno = arg.lineno
            assert mv.lineno > 0
            pred.insert_stm(-1, mv)
            logger.debug('PHI divide into ' + str(mv))
            #update usedef table
            if arg.is_a(TEMP):
                usedef.remove_var_use(arg, phi)
                usedef.add_var_use(mv.src, mv)
            elif arg.is_a(CONST):
                usedef.remove_const_use(arg, phi)
                usedef.add_const_use(mv.src, mv)

            usedef.add_var_def(mv.dst, mv)

        usedef.remove_var_def(phi.var, phi)
        phi.block.stms.remove(phi)
        self.phis.remove(phi)

        #assert len(usedef.get_def_stms_by_sym(phi.var.sym)) == len(phi.argv())
