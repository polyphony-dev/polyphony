from collections import deque, defaultdict
from .varreplacer import VarReplacer
from .ir import *
from .symbol import Symbol
from .type import Type
from .irvisitor import IRTransformer, IRVisitor
from .env import env
from .scope import Scope
from logging import getLogger
logger = getLogger(__name__)
import pdb


class MemoryRenamer:
    def _collect_def_mem_stm(self, scope):
        stms = []
        for block in scope.traverse_blocks():
            for stm in block.stms:
                if stm.is_a(MOVE):
                    if stm.src.is_a(ARRAY):
                        stms.append(stm)
                    elif stm.src.is_a(TEMP) and stm.src.sym.is_param() and Type.is_list(stm.src.sym.typ):
                        stms.append(stm)
        return stms

    def _get_phis(self, block):
        return filter(lambda stm: stm.is_a(PHI) and Type.is_list(stm.var.symbol().typ), block.stms)

    def _cleanup_phi(self):
        for block in self.scope.traverse_blocks():
            remove_phis = []
            for phi in self._get_phis(block):
                remove_args = []
                args = set()
                for arg in phi.args:
                    args.add(arg.sym)
                    if arg.is_a(TEMP) and arg.symbol() is phi.var.symbol():
                        remove_args.append(arg)
                if len(args) == 1:
                    remove_phis.append(phi)
                    continue
                for arg in remove_args:
                    phi.remove_arg(arg)
            for phi in remove_phis:
                block.stms.remove(phi)

    def process(self, scope):
        self.scope = scope
        usedef = scope.usedef
        worklist = deque()
        stms = self._collect_def_mem_stm(scope)
        mem_var_map = defaultdict(set)
        memsrcs = []#tuple([mv.dst.sym for mv in stms])

        for mv in stms:
            logger.debug('!!! mem def stm ' + str(mv))
            assert mv.src.is_a(ARRAY) \
                or (mv.src.is_a(TEMP) and mv.src.sym.is_param())

            memsym = mv.dst.symbol()
            memsrcs.append(memsym)
            uses = usedef.get_use_stms_by_sym(memsym)
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
            if stm.is_a(MOVE):
                if stm.src.is_a(TEMP):
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

                elif stm.src.is_a(MSTORE):
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

            elif stm.is_a(PHI):
                updated = False
                for arg in stm.args:
                    if arg.symbol() in mem_var_map:
                        updated = merge_mem_var(arg, stm.var)
                    elif arg.symbol() in memsrcs:
                        mem = arg.symbol()
                        if stm.var.symbol() != mem and (stm.var.symbol() not in mem_var_map or mem not in mem_var_map[stm.var.symbol()]):
                            mem_var_map[stm.var.symbol()].add(mem)
                            updated = True
                # reach fix point ?
                if not updated and stm in dones:
                    continue
                sym = stm.var.symbol()

            if sym:
                uses = usedef.get_use_stms_by_sym(sym)
                worklist.extend(list(uses))
                for u in uses:
                    for var in usedef.get_use_vars_by_stm(u):
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
            if mv.src.is_a(TEMP):
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

class ContextModifier(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_CALL(self, ir):
        for arg in ir.args:
            if arg.is_a(TEMP) and Type.is_list(arg.sym.typ):
                memnode = Type.extra(arg.sym.typ)
                # FIXME: check the memnode is locally writable or not
                if memnode.is_writable():
                    arg.ctx = Ctx.LOAD | Ctx.STORE

class RomDetector:
    def _propagate_writable_flag(self):
        for node in self.mrg.collect_top_module_nodes():
            node.set_writable()
        worklist = deque()
        for source in self.mrg.collect_sources():
            if source.is_writable():
                source.propagate_succs(lambda n: n.set_writable())
            else:
                worklist.append(source)

        checked = set()
        while worklist:
            node = worklist.popleft()
            if node not in checked and node.is_writable():
                checked.add(node)
                sources = set([source for source in node.sources()])
                unchecked_sources = sources.difference(checked)
                for s in unchecked_sources:
                    s.propagate_succs(lambda n: n.set_writable() or checked.add(n))
            else:
                unchecked_succs = set(node.succ_ref_nodes()).difference(checked)
                worklist.extend(unchecked_succs)

    def _propagate_info(self):
        for source in self.mrg.collect_sources():
            source.propagate_succs(lambda n: n.update())

    def process_all(self):
        self.mrg = env.memref_graph
        self._propagate_info()
        self._propagate_writable_flag()

