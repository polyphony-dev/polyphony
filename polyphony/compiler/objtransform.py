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
        def _find_root_def(sym, copy_sym):
            if sym in defs:
                assert copy_sym.ancestor
                return {sym}
            elif sym.ancestor and sym.ancestor in copy_sources:
                return copy_sources[sym.ancestor]
            return set()
        copy_sources = defaultdict(set)
        for sym, stm in copies.items():
            if stm.is_a(MOVE) and stm.src.is_a([TEMP, ATTR]):
                roots = _find_root_def(stm.src.symbol(), sym)
                copy_sources[sym.ancestor] |= roots
            elif stm.is_a(PHIBase):
                for arg in stm.args:
                    roots = _find_root_def(arg.symbol(), sym)
                    copy_sources[sym.ancestor] |= roots
        return copy_sources

    def _transform_obj_access(self):
        self._transform_use(self.obj_copies, self.obj_copy_sources)
        self._transform_use(self.seq_copies, self.seq_copy_sources)
        self._transform_seq_ctor()

    def _transform_use(self, copies, copy_sources):
        for copy_sym, copy_stm in copies.items():
            sources = copy_sources[copy_sym.ancestor]
            usestms = self.scope.usedef.get_stms_using(copy_sym).copy()
            for stm in usestms:
                if not stm.is_a([MOVE, EXPR]):
                    continue
                self.udupdater.update(stm, None)
                if copy_stm.is_a(PHIBase) and stm.is_a(MOVE):
                    self._add_uphi(stm, sources, copy_sym)
                elif stm.is_a(EXPR):
                    self._add_cexpr(stm, sources, copy_sym)

    def _add_uphi(self, mv_stm, sources, copy_sym):
        insert_idx = mv_stm.block.stms.index(mv_stm)
        tmp = self.scope.add_temp('{}_{}'.format(Symbol.temp_prefix,
                                  copy_sym.orig_name()))
        var = TEMP(tmp, Ctx.STORE)
        uphi = UPHI(var)
        for src in sources:
            c = RELOP('Eq',
                      TEMP(copy_sym, Ctx.LOAD),
                      TEMP(src, Ctx.LOAD))
            c_sym = self.scope.add_condition_sym()
            tmp = TEMP(c_sym, Ctx.STORE)
            tmp_mv = MOVE(tmp, c, loc=mv_stm.loc)
            mv_stm.block.insert_stm(insert_idx, tmp_mv)
            insert_idx += 1
            self.udupdater.update(None, tmp_mv)
            uphi.ps.append(TEMP(c_sym, Ctx.LOAD))
            mv_src = mv_stm.src.clone()
            mv_src.replace(copy_sym, src)
            uphi.args.append(mv_src)
        mv_stm.block.insert_stm(insert_idx, uphi)
        self.udupdater.update(None, uphi)
        var = var.clone()
        var.ctx = Ctx.LOAD
        mv_stm.src = var

    def _add_cexpr(self, expr, sources, copy_sym):
        insert_idx = expr.block.stms.index(expr)
        for src in sources:
            expr_copy = expr.clone()
            expr_copy.replace(copy_sym, src)
            c = RELOP('Eq',
                      TEMP(copy_sym, Ctx.LOAD),
                      TEMP(src, Ctx.LOAD))
            cexpr = CEXPR(c, expr_copy.exp, loc=expr_copy.loc)
            expr.block.insert_stm(insert_idx, cexpr)
            self.udupdater.update(None, cexpr)
        expr.block.stms.remove(expr)

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
                        and not usestm.src.is_a([MREF, SYSCALL])):
                    usestm.replace(seq_sym, seq_id)
                elif (usestm.is_a(CMOVE)
                        and usestm.cond.find_vars((seq_sym,))):
                    usestm.cond.replace(seq_sym, seq_id)
                elif (usestm.is_a(CEXPR)
                        and usestm.cond.find_vars((seq_sym,))):
                    usestm.cond.replace(seq_sym, seq_id)
                elif usestm.is_a([LPHI, PHI]):
                    usestm.replace(seq_sym, seq_id)
        for seq_sym in self.seq_copies.keys():
            seq_sym.set_type(Type.int(16))