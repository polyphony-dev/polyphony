from .graph import Graph
from .ir import *
from logging import getLogger
logger = getLogger(__name__)


class PHICondResolver(object):
    def process(self, scope):
        self.scope = scope
        self._collect_phi()
        for phis in self.phis.values():
            if len(phis) > 1:
                phis = self._sort_phis(phis)
            if not phis:
                assert False  # TODO:
            for phi in phis:
                if phi.is_a(PHI):
                    # TODO:
                    #self._divide_phi_to_mv(phi)
                    continue
                elif phi.is_a(LPHI):
                    self._divide_phi_to_mv(phi)
                    continue

    def _collect_phi(self):
        self.phis = {}
        for b in self.scope.traverse_blocks():
            phis = b.collect_stms([PHI, LPHI])
            if phis:
                self.phis[b] = phis

    def _sort_phis(self, phis):
        interference_graph = Graph()
        for phi in phis:
            interference_graph.add_node(phi)
            phi_set = set(phis)
            phi_set.discard(phi)
            usestms = self.scope.usedef.get_stms_using(phi.var.symbol())
            usephis = usestms & phi_set
            if usephis:
                for stm in usephis:
                    interference_graph.add_edge(stm, phi)
        sorted_phis = []
        for n in interference_graph.bfs_ordered_nodes():
            sorted_phis.append(n)
        return sorted_phis

    def _divide_phi_to_mv(self, phi):
        for arg, pred in zip(phi.args, phi.block.preds):
            if phi.var.symbol().typ.is_object():
                continue
            self._insert_mv(phi.var.clone(), arg, pred)
        phi.block.stms.remove(phi)

    def _insert_mv(self, var, arg, blk):
        mv = MOVE(var, arg)
        mv.lineno = arg.lineno
        mv.dst.lineno = arg.lineno
        assert mv.lineno >= 0
        blk.insert_stm(-1, mv)
        logger.debug('PHI divide into ' + str(mv) + ' ' + blk.name)
