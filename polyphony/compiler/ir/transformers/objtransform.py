from collections import defaultdict, deque
from ..block import Block
from ..builtin import builtin_symbols
from ..ir import *
from ..type import Type
from ..analysis.usedef import UseDefUpdater
from ...common.utils import replace_item
from logging import getLogger
logger = getLogger(__name__)


class ObjectTransformer(object):
    def process(self, scope):
        self.udupdater = UseDefUpdater(scope)
        self.scope = scope
        self._collect_obj_defs()
        self._collect_copy_sources()
        self._transform_obj_access()
        Block.set_order(scope.entry_block, 0)

    def _collect_obj_defs(self):
        self.obj_defs = set()
        self.obj_copies = {}
        self.seq_defs = set()
        self.seq_copies = {}
        for blk in self.scope.traverse_blocks():
            for stm in blk.collect_stms([MOVE, PHI, LPHI, UPHI]):
                if stm.is_a(MOVE):
                    qsym = stm.dst.qualified_symbol()
                    typ = qsym[-1].typ
                    if typ.is_object():
                        if stm.src.is_a(SYSCALL) and stm.src.sym is builtin_symbols['$new']:
                            self.obj_defs.add(qsym[-1])
                        elif stm.src.is_a(TEMP) and stm.src.sym.is_param():
                            pass
                        else:
                            self.obj_copies[qsym] = stm
                    elif typ.is_seq():
                        if stm.src.is_a(ARRAY):
                            self.seq_defs.add(qsym[-1])
                        elif stm.src.is_a(TEMP) and stm.src.sym.is_param():
                            pass
                        else:
                            self.seq_copies[qsym] = stm
                elif stm.is_a(PHIBase):
                    qsym = stm.var.qualified_symbol()
                    typ = qsym[-1].typ
                    if typ.is_object():
                        self.obj_copies[qsym] = stm
                    elif typ.is_seq():
                        self.seq_copies[qsym] = stm

    def _collect_copy_sources(self):
        self.obj_copy_sources = self._collect_sources(self.obj_copies, self.obj_defs)
        self.seq_copy_sources = self._collect_sources(self.seq_copies, self.seq_defs)
        #print('obj_defs', self.obj_defs)
        #print('obj_copy_sources', self.obj_copy_sources)
        #print('seq_defs', self.seq_defs)
        #print('seq_copy_sources', self.seq_copy_sources)

    def qsym_ancestor(self, qsym):
        return tuple([sym.ancestor for sym in qsym])

    def qsym_name(self, qsym):
        return '_'.join([sym.name for sym in qsym])

    def qsym_to_ir(self, qsym, ctx):
        ir = TEMP(qsym[0], Ctx.LOAD)
        for i, sym in enumerate(qsym[1:]):
            if i == len(qsym) - 1:
                ir = ATTR(ir, sym, ctx)
            else:
                ir = ATTR(ir, sym, Ctx.LOAD)
        return ir

    def _collect_sources(self, copies, defs):
        def _find_root_def(qsym, copy_qsym):
            if qsym[-1] in defs:
                assert copy_qsym[-1].ancestor
                return {qsym[-1]}
            elif qsym[-1].ancestor and self.qsym_ancestor(qsym) in copy_sources:
                return copy_sources[self.qsym_ancestor(qsym)]
            else:
                return None

        if not defs:
            return
        copy_sources = defaultdict(set)
        worklist = deque()
        for copy_qsym, stm in copies.items():
            if stm.is_a(MOVE) and stm.src.is_a([TEMP, ATTR]):
                worklist.append((stm.src.qualified_symbol(), copy_qsym))
            elif stm.is_a(PHIBase):
                for arg in stm.args:
                    worklist.append((arg.qualified_symbol(), copy_qsym))
        while worklist:
            qsym, copy_qsym = worklist.popleft()
            roots = _find_root_def(qsym, copy_qsym)
            if roots is None:
                worklist.append((qsym, copy_qsym))
                continue
            copy_sources[self.qsym_ancestor(copy_qsym)] |= roots
        return copy_sources

    def _transform_obj_access(self):
        self._transform_use(self.obj_copies, self.obj_copy_sources)
        self._transform_use(self.seq_copies, self.seq_copy_sources)
        self._transform_seq_ctor()

    def _find_use_var(self, stm, qsym):
        max_len = 0
        var = None
        for use_var in self.scope.usedef.get_vars_used_at(stm):
            qsym_ = use_var.qualified_symbol()
            if len(qsym_) > max_len:
                var = use_var
                max_len = len(qsym_)
        if var.qualified_symbol()[:-1] == qsym:
            return var
        return None

    def _find_def_var(self, stm, qsym):
        max_len = 0
        var = None
        for def_var in self.scope.usedef.get_vars_defined_at(stm):
            qsym_ = def_var.qualified_symbol()
            if len(qsym_) > max_len:
                var = def_var
                max_len = len(qsym_)
        if var.qualified_symbol()[:-1] == qsym:
            return var
        return None

    def _transform_use(self, copies, copy_sources):
        if not copy_sources:
            return
        for copy_qsym, copy_stm in copies.items():
            sources = copy_sources[self.qsym_ancestor(copy_qsym)]
            usestms = self.scope.usedef.get_stms_using(copy_qsym).copy()
            for stm in usestms:
                if not stm.is_a([MOVE, EXPR]):
                    continue
                if copy_stm.is_a(PHIBase) and stm.is_a(MOVE):
                    use_var = self._find_use_var(stm, copy_qsym)
                    if use_var or stm.src.is_a(MREF) or (stm.src.is_a(SYSCALL) and stm.src.sym.name == 'len'):
                        # y = obj.x  -->  y = uphi(c0 ? obj0.x,
                        #                          c1 ? obj1.x)
                        self._add_uphi(stm, sources, copy_qsym)

                    def_var = self._find_def_var(stm, copy_qsym)
                    if def_var:
                        # CMOVE cannot be used here
                        # because scalar SSA transform is done after this.
                        # obj.x = y  --> if c0:
                        #                    obj0.x = y
                        #                 elif c1:
                        #                    obj1.x = y
                        self._add_branch_move(stm, sources, copy_qsym)
                elif stm.is_a(EXPR):
                    # obj.f()  -->  c0 ? obj0.f()
                    #               c1 ? obj1.f()
                    self._add_cexpr(stm, sources, copy_qsym)

    def _add_uphi(self, mv_stm, sources, copy_qsym):
        self.udupdater.update(mv_stm, None)
        insert_idx = mv_stm.block.stms.index(mv_stm)
        tmp = self.scope.add_temp()
        var = TEMP(tmp, Ctx.STORE)
        uphi = UPHI(var)
        for src in sources:
            c = RELOP('Eq',
                      self.qsym_to_ir(copy_qsym, Ctx.LOAD), #copy_var.clone(),
                      TEMP(src, Ctx.LOAD))
            c_sym = self.scope.add_condition_sym()
            tmp = TEMP(c_sym, Ctx.STORE)
            tmp_mv = MOVE(tmp, c, loc=mv_stm.loc)
            mv_stm.block.insert_stm(insert_idx, tmp_mv)
            insert_idx += 1
            self.udupdater.update(None, tmp_mv)
            uphi.ps.append(TEMP(c_sym, Ctx.LOAD))
            mv_src = mv_stm.src.clone()
            #mv_src.replace(copy_var.exp, TEMP(src, Ctx.LOAD))
            mv_src.replace(self.qsym_to_ir(copy_qsym, Ctx.LOAD), TEMP(src, Ctx.LOAD))
            uphi.args.append(mv_src)
        mv_stm.block.insert_stm(insert_idx, uphi)
        self.udupdater.update(None, uphi)
        self.udupdater.update(mv_stm, None)
        var = var.clone()
        var.ctx = Ctx.LOAD
        mv_stm.src = var
        self.udupdater.update(None, mv_stm)

    def _add_branch_move(self, mv_stm, sources, copy_qsym):
        self.udupdater.update(mv_stm, None)
        blk = mv_stm.block
        is_exit = self.scope.exit_block is blk
        stm_idx = blk.stms.index(mv_stm)
        # add moves for condition variable
        csyms = []
        for src in sources:
            # Must follow Quadruplet form
            cond_rhs = RELOP('Eq',
                             self.qsym_to_ir(copy_qsym, Ctx.LOAD), #copy_var.exp.clone(),
                             TEMP(src, Ctx.LOAD))
            csym = self.scope.add_condition_sym()
            cond_lhs = TEMP(csym, Ctx.STORE)
            mv = MOVE(cond_lhs, cond_rhs, loc=mv_stm.loc)
            blk.insert_stm(stm_idx, mv)
            self.udupdater.update(None, mv)
            csyms.append(csym)
        stm_idx = blk.stms.index(mv_stm)
        # add branching
        for src, csym in zip(sources, csyms):
            mv_copy = mv_stm.clone()
            mv_copy.dst.exp = TEMP(src, Ctx.STORE)
            new_tail = self._make_branch(TEMP(csym, Ctx.LOAD), mv_copy, blk, stm_idx)
            stm_idx = 0
            blk = new_tail
            self.udupdater.update(None, mv_copy)
        mv_stm.block.stms.remove(mv_stm)
        if is_exit:
            self.scope.exit_block = blk

    def _make_branch(self, cond, branch_stm, cur_blk, stm_idx):
        # make block and connection
        branch_blk = Block(self.scope)
        tail_blk = Block(self.scope)
        tail_blk.succs = cur_blk.succs[:]
        tail_blk.succs_loop = cur_blk.succs_loop[:]
        tail_blk.preds = [branch_blk, cur_blk]
        if cur_blk.path_exp and not cur_blk.path_exp.is_a(CONST):
            tail_blk.path_exp = cur_blk.path_exp.clone()
        else:
            tail_blk.path_exp = CONST(1)
        for succ in cur_blk.succs:
            replace_item(succ.preds, cur_blk, tail_blk)
        cur_blk.succs = [branch_blk, tail_blk]
        branch_blk.preds = [cur_blk]
        branch_blk.succs = [tail_blk]
        if cur_blk.path_exp and not cur_blk.path_exp.is_a(CONST):
            branch_blk.path_exp = RELOP('And', cond.clone(), cur_blk.path_exp.clone())
        else:
            branch_blk.path_exp = cond.clone()
        # split stms
        for stm in cur_blk.stms[stm_idx:]:
            tail_blk.append_stm(stm)
        cur_blk.stms = cur_blk.stms[:stm_idx]

        cj = CJUMP(cond, branch_blk, tail_blk, loc=branch_stm.loc)
        cur_blk.append_stm(cj)

        branch_blk.append_stm(branch_stm)
        branch_blk.append_stm(JUMP(tail_blk, loc=branch_stm.loc))
        return tail_blk

    def _add_cexpr(self, expr, sources, copy_qsym):
        self.udupdater.update(expr, None)
        insert_idx = expr.block.stms.index(expr)
        for src in sources:
            expr_copy = expr.clone()
            if expr_copy.exp.is_a(MSTORE):
                expr_copy.exp.mem = TEMP(src, Ctx.LOAD)
            else:
                raise NotImplemented
            c = RELOP('Eq',
                      self.qsym_to_ir(copy_qsym, Ctx.LOAD),
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
            seq_sym[-1].typ = Type.int(16)
