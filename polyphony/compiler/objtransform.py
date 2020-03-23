from collections import defaultdict
from .builtin import builtin_symbols
from .ir import *
from .usedef import UseDefUpdater
from .type import Type
from logging import getLogger
logger = getLogger(__name__)


class ObjectTransformer(object):
    def process(self, scope):
        self.udupdater = UseDefUpdater(scope)
        self.scope = scope
        self._collect_obj_defs()
        self._collect_copy_sources()
        self._transform_obj_access()

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
        self.obj_copy_sources = self._collect_sources(self.obj_copies, self.obj_defs)
        self.seq_copy_sources = self._collect_sources(self.seq_copies, self.seq_defs)

    def _collect_sources(self, copies, defs):
        copy_sources = defaultdict(set)
        for sym, stm in copies.items():
            if stm.is_a(MOVE) and stm.src.is_a([TEMP, ATTR]):
                if stm.src.symbol() in defs:
                    assert sym.ancestor
                    copy_sources[sym.ancestor].add(stm.src.symbol())
            elif stm.is_a(PHIBase):
                for arg in stm.args:
                    if arg.symbol() in defs:
                        assert sym.ancestor
                        copy_sources[sym.ancestor].add(arg.symbol())
        return copy_sources

    def _transform_obj_access(self):
        self._transform_use(self.obj_copies, self.obj_copy_sources)
        self._transform_use(self.seq_copies, self.seq_copy_sources)
        self._transform_seq_ctor()

    def _transform_use(self, copies, copy_sources):
        for copy_sym in copies.keys():
            sources = copy_sources[copy_sym.ancestor]
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

    def _transform_seq_ctor(self):
        for seq_sym in self.seq_defs:
            defstms = self.scope.usedef.get_stms_defining(seq_sym)
            defstm = list(defstms)[0]
            assert defstm.src.is_a(ARRAY)

            seq_id = self.scope.add_sym(f'{seq_sym.name}__id', tags=set(), typ=Type.int(16))
            mv = MOVE(TEMP(seq_id, Ctx.STORE),
                      CONST(seq_id.id),
                      loc=defstm.loc)
            idx = defstm.block.stms.index(defstm)
            defstm.block.insert_stm(idx, mv)

            usestms = self.scope.usedef.get_stms_using(seq_sym)
            for usestm in usestms:
                if (usestm.is_a(MOVE)
                        and usestm.src.is_a([TEMP, ATTR])
                        and usestm.src.symbol() is seq_sym):
                    usestm.replace(seq_sym, seq_id)
                elif (usestm.is_a(CMOVE)
                        and usestm.cond.find_vars((seq_sym,))):
                    usestm.cond.replace(seq_sym, seq_id)
                elif (usestm.is_a(CEXPR)
                        and usestm.cond.find_vars((seq_sym,))):
                    usestm.cond.replace(seq_sym, seq_id)
                elif usestm.is_a(PHIBase):
                    usestm.replace(seq_sym, seq_id)
        for seq_sym in self.seq_copies.keys():
            seq_sym.set_type(Type.int(16))