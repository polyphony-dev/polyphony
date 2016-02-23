from collections import deque, defaultdict
from .varreplacer import VarReplacer
from .ir import CONST, TEMP, ARRAY, CALL, EXPR, MREF, MSTORE, MOVE, PHI
from .symbol import Symbol
from .type import Type
from .irvisitor import IRTransformer, IRVisitor
from .env import env
from logging import getLogger
logger = getLogger(__name__)
import pdb


class MemoryRenamer:
    def _collect_def_mem_stm(self, scope):
        stms = []
        for block in scope.blocks:
            for stm in block.stms:
                if isinstance(stm, MOVE):
                    if isinstance(stm.src, ARRAY):
                        stms.append(stm)
                    elif isinstance(stm.src, TEMP) and stm.src.sym.is_param() and Type.is_list(stm.src.sym.typ):
                        stms.append(stm)
        return stms

    def _get_phis(self, block):
        return filter(lambda stm: isinstance(stm, PHI), block.stms)

    def _cleanup_phi(self):
        for block in self.scope.blocks:
            remove_phis = []
            for phi in self._get_phis(block):
                remove_args = []
                args = set()
                for arg, blk in phi.args:
                    args.add(arg.sym)
                    if isinstance(arg, TEMP) and arg.sym is phi.var.sym:
                        remove_args.append((arg, blk))
                if len(args) == 1:
                    remove_phis.append(phi)
                    continue
                for arg in remove_args:
                    phi.args.remove(arg)
            for phi in remove_phis:
                block.stms.remove(phi)

    def process(self, scope):
        self.scope = scope
        usedef = scope.usedef
        worklist = deque()
        stms = self._collect_def_mem_stm(scope)
        mem_var_map = defaultdict(set)
        memsrcs = tuple([mv.dst.sym for mv in stms])

        for mv in stms:
            logger.debug('!!! mem def stm ' + str(mv))
            assert isinstance(mv.src, ARRAY) \
                or (isinstance(mv.src, TEMP) and mv.src.sym.is_param())
            uses = usedef.get_sym_uses_stm(mv.dst.sym)
            worklist.extend(list(uses))

        def merge_mem_var(src, dst):
            src_mems = mem_var_map[src.sym]
            if dst.sym in src_mems:
                src_mems.remove(dst.sym)
            dst_mems = mem_var_map[dst.sym]
            if len(src_mems) > 1:
                # this src is joined reference
                mem_var_map[dst.sym] = dst_mems.union(set([src.sym]))
            else:
                mem_var_map[dst.sym] = dst_mems.union(src_mems)
            return len(mem_var_map[dst.sym]) != len(dst_mems)

        dones = set()
        moves = set()
        sym2var = defaultdict(set)
        while worklist:
            stm = worklist.popleft()
            sym = None
            if isinstance(stm, MOVE):
                if isinstance(stm.src, TEMP):
                    moves.add(stm)
                    if stm.src.sym in mem_var_map:
                        updated = merge_mem_var(stm.src, stm.dst)
                        sym2var[stm.dst.sym].add(stm.dst)
                        if not updated and stm in dones:
                            # reach fix point ?
                            continue
                    else:
                        assert stm.src.sym in memsrcs
                        mem = stm.src.sym
                        if stm.dst.sym in mem_var_map and mem in mem_var_map[stm.dst.sym] and stm in dones:
                            # reach fix point ?
                            continue
                        mem_var_map[stm.dst.sym].add(mem)
                        sym2var[stm.dst.sym].add(stm.dst)

                    sym = stm.dst.sym

                elif isinstance(stm.src, MSTORE):
                    if stm.src.mem.sym in mem_var_map:
                        updated = merge_mem_var(stm.src.mem, stm.dst)
                        sym2var[stm.dst.sym].add(stm.dst)
                        if not updated:
                            # reach fix point ?
                            if stm in dones:
                                continue
                    else:
                        assert stm.src.mem.sym in memsrcs
                        mem = stm.src.mem.sym
                        if stm.dst.sym in mem_var_map and mem in mem_var_map[stm.dst.sym] and stm in dones:
                            # reach fix point ?
                            continue
                        mem_var_map[stm.dst.sym].add(mem)
                        sym2var[stm.dst.sym].add(stm.dst)

                    sym = stm.dst.sym

            elif isinstance(stm, PHI):
                updated = False
                for arg, blk in stm.args:
                    if arg.sym in mem_var_map:
                        updated = merge_mem_var(arg, stm.var)
                    elif arg.sym in memsrcs:
                        mem = arg.sym
                        if stm.var.sym != mem and (stm.var.sym not in mem_var_map or mem not in mem_var_map[stm.var.sym]):
                            mem_var_map[stm.var.sym].add(mem)
                            updated = True
                # reach fix point ?
                if not updated and stm in dones:
                    continue
                sym = stm.var.sym

            if sym:
                uses = usedef.get_sym_uses_stm(sym)
                worklist.extend(list(uses))
                for u in uses:
                    for var in usedef.get_stm_uses_var(u):
                        if var.sym is sym:
                            sym2var[var.sym].add(var)

            dones.add(stm)

        for sym, mems in mem_var_map.items():
            logger.debug(str(sym) + '<---' + ','.join([str(m) for m in mems]))
            if len(mems) == 1:
                m = mems.pop()
                for v in sym2var[sym]:
                    v.sym = m

        for mv in moves:
            if isinstance(mv.src, TEMP):
                if mv.dst.sym is mv.src.sym:
                    mv.block.stms.remove(mv)
        self._cleanup_phi()


class MemCollector(IRVisitor):
    def __init__(self):
        super().__init__()
        self.stm_map = defaultdict(list)

    def visit_TEMP(self, ir):
        if Type.is_list(ir.sym.typ) and not ir.sym.is_param():
            self.stm_map[ir.sym].append(self.current_stm)

class RomDetector:
    def process_all(self):
        mrg = env.memref_graph
        assert mrg
        worklist = deque()
        for root in mrg.collect_roots():
            if root.is_writable():
                root.propagate_succs(lambda n: n.set_writable())
            else:
                worklist.append(root)

        checked = set()
        while worklist:
            node = worklist.popleft()
            if node not in checked and node.is_writable():
                checked.add(node)
                roots = set([root for root in mrg.collect_node_roots(node)])
                unchecked_roots = [root for root in roots if root not in checked]
                for r in unchecked_roots:
                    r.propagate_succs(lambda n: n.set_writable() or checked.add(n))
            else:
                unchecked_succs = filter(lambda n: n not in checked, node.succs)
                worklist.extend(unchecked_succs)

