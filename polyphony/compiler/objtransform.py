from collections import defaultdict
from .builtin import builtin_symbols
from .ir import *
from .irhelper import reduce_relexp
from .usedef import UseDefUpdater
from logging import getLogger
logger = getLogger(__name__)


class ObjectTransformer(object):
    def process(self, scope):
        self.udupdater = UseDefUpdater(scope)
        self.scope = scope
        self._collect_obj_defs()
        self._collect_copy_sources()
        self._transform_use()

    def _collect_obj_defs(self):
        self.obj_defs = set()
        self.obj_copies = {}
        self.seq_defs = set()
        self.seq_copies = {}
        for blk in self.scope.traverse_blocks():
            for stm in blk.collect_stms([MOVE, PHI, LPHI, UPHI]):
                if stm.is_a(MOVE):
                    sym = stm.dst.symbol()
                    if sym.typ.is_object():
                        if stm.src.is_a(SYSCALL) and stm.src.sym is builtin_symbols['$new']:
                            self.obj_defs.add(sym)
                        else:
                            self.obj_copies[sym] = stm
                    elif sym.typ.is_seq():
                        if stm.src.is_a(ARRAY):
                            self.seq_defs.add(sym)
                        else:
                            self.seq_copies[sym] = stm
                elif stm.is_a(PHIBase):
                    sym = stm.var.symbol()
                    if sym.typ.is_object():
                        self.obj_copies[sym] = stm
                    elif sym.typ.is_seq():
                        self.seq_copies[sym] = stm

    def _collect_copy_sources(self):
        self.copy_sources = defaultdict(set)
        for sym, stm in self.obj_copies.items():
            if stm.is_a(MOVE):
                if stm.src.symbol() in self.obj_defs:
                    assert sym.ancestor
                    self.copy_sources[sym.ancestor].add(stm.src.symbol())
            elif stm.is_a(PHIBase):
                for arg in stm.args:
                    if arg.symbol() in self.obj_defs:
                        assert sym.ancestor
                        self.copy_sources[sym.ancestor].add(arg.symbol())

    def _transform_use(self):
        for copy_sym in self.obj_copies.keys():
            sources = self.copy_sources[copy_sym.ancestor]
            usestms = self.scope.usedef.get_stms_using(copy_sym).copy()
            for stm in usestms:
                if not stm.is_a([MOVE, EXPR]):
                    continue
                idx = stm.block.stms.index(stm)
                stm.block.stms.remove(stm)
                block = stm.block
                self.udupdater.update(stm, None)
                for src in sources:
                    stm_copy = stm.clone()
                    stm_copy.replace(copy_sym, src)
                    c = RELOP('Eq',
                              TEMP(copy_sym, Ctx.LOAD),
                              TEMP(src, Ctx.LOAD))
                    if stm_copy.is_a(MOVE):
                        cstm = CMOVE(c, stm_copy.dst, stm_copy.src, loc=stm_copy.loc)
                    elif stm_copy.is_a(EXPR):
                        cstm = CEXPR(c, stm_copy.exp, loc=stm_copy.loc)

                    block.insert_stm(idx, cstm)
                    self.udupdater.update(None, cstm)
