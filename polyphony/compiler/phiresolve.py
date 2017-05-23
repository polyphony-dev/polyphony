from .ir import *
from .irvisitor import IRVisitor
from logging import getLogger
logger = getLogger(__name__)


class PHICondResolver(object):
    def __init__(self):
        self.count = 0

    def process(self, scope):
        self.scope = scope
        self._collect_phi()
        phis = self.phis[:]
        for phi in phis:
            if (phi.is_a(PHI) and
                    (not phi.block.is_hyperblock or not phi.var.symbol().typ.is_scalar())):
                self._divide_phi_to_mv(phi)
                continue
            elif phi.is_a(LPHI):
                self._divide_phi_to_mv(phi)
                continue

    def _collect_phi(self):
        self.phis = []
        for b in self.scope.traverse_blocks():
            phis = b.collect_stms([PHI, LPHI])
            self.phis.extend(phis)

    def _divide_phi_to_mv(self, phi):
        for arg, blk in zip(phi.args, phi.defblks):
            if not blk:
                continue
            if phi.var.symbol().typ.is_object():
                continue
            self._insert_mv(phi.var.clone(), arg, blk)
        phi.block.stms.remove(phi)
        self.phis.remove(phi)

    def _insert_mv(self, var, arg, blk):
        mv = MOVE(var, arg)
        mv.lineno = arg.lineno
        mv.iorder = arg.iorder
        mv.dst.lineno = arg.lineno
        assert mv.lineno > 0
        idx = self._find_stm_insetion_index(blk, mv)
        blk.insert_stm(idx, mv)
        logger.debug('PHI divide into ' + str(mv) + ' ' + blk.name)

    def _find_stm_insetion_index(self, block, target_stm):
        for i, stm in enumerate(block.stms):
            if stm.iorder > target_stm.iorder:
                return i
        return -1


class StmOrdering(IRVisitor):
    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if ir.is_a(IRStm):
            ir.iorder = ir.block.stms.index(ir)
        else:
            ir.iorder = self.current_stm.iorder
        visitor(ir)
