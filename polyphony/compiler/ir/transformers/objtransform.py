"""ObjectTransformer using new IR (ir.py)."""
from collections import defaultdict, deque
from ..block import Block
from ..ir import Loc
from ..ir import (
    Ir, IrVariable, IrNameExp, Temp, Attr, Const, Move, CMove, Expr, CExpr,
    MRef, MStore, MStm, SysCall, Array, RelOp, CJump, Jump,
    Phi, UPhi, LPhi, Ctx,
)
from ..irhelper import qualified_symbols, irexp_type
from ..types.type import Type
from ..analysis.usedef import UseDefDetector, UseDefUpdater
from ..analysis.usedef import UseDefItem
from ...common.utils import replace_item
from ...common.env import env
from logging import getLogger
logger = getLogger(__name__)


class ObjectTransformer(object):
    def process(self, scope):
        self.scope = scope
        self.seq_id_map = {}
        self.usedef = UseDefDetector().process(scope)
        self._collect_obj_defs()
        self._collect_copy_sources()
        self._transform_obj_access()
        Block.set_order(scope.entry_block, 0)

    def _collect_obj_defs(self):
        self.obj_defs = set()
        self.obj_copies = {}
        self.seq_defs = set()
        self.seq_copies = {}
        from ..symbol import Symbol
        for blk in self.scope.traverse_blocks():
            for stm in blk.stms:
                if isinstance(stm, Move):
                    dst_typ = irexp_type(stm.dst, self.scope)
                    if dst_typ.is_object():
                        qsym = qualified_symbols(stm.dst, self.scope)
                        assert isinstance(qsym[-1], Symbol)
                        if isinstance(stm.src, SysCall) and stm.src.name == '$new':
                            self.obj_defs.add(qsym[-1])
                        elif isinstance(stm.src, Temp) and self.scope.find_sym(stm.src.name).is_param():
                            pass
                        else:
                            self.obj_copies[qsym] = stm
                    elif dst_typ.is_seq():
                        assert not isinstance(stm.dst, Array)
                        qsym = qualified_symbols(stm.dst, self.scope)
                        assert isinstance(qsym[-1], Symbol)
                        if isinstance(stm.src, Array):
                            self.seq_defs.add(qsym[-1])
                        elif isinstance(stm.src, Temp) and self.scope.find_sym(stm.src.name).is_param():
                            pass
                        else:
                            self.seq_copies[qsym] = stm
                elif isinstance(stm, (Phi, UPhi, LPhi)):
                    qsym = qualified_symbols(stm.var, self.scope)
                    from ..symbol import Symbol
                    assert isinstance(qsym[-1], Symbol)
                    typ = qsym[-1].typ
                    if typ.is_object():
                        self.obj_copies[qsym] = stm
                    elif typ.is_seq():
                        self.seq_copies[qsym] = stm

    def _collect_copy_sources(self):
        self.obj_copy_sources = self._collect_sources(self.obj_copies, self.obj_defs)
        self.seq_copy_sources = self._collect_sources(self.seq_copies, self.seq_defs)

    def qsym_ancestor(self, qsym):
        return tuple(env.origin_registry.sym_origin_of(sym) for sym in qsym)

    def qsym_name(self, qsym):
        return '_'.join(sym.name for sym in qsym)

    def _src_cmp_name(self, src):
        """Get the name to use in equality comparisons for a source symbol.
        For sequences, use the seq_id name instead of the original name."""
        return self.seq_id_map.get(src.name, src.name)

    def qsym_to_ir(self, qsym, ctx):
        ir = Temp(name=qsym[0].name, ctx=Ctx.LOAD)
        for i, sym in enumerate(qsym[1:]):
            c = ctx if i == len(qsym) - 2 else Ctx.LOAD
            ir = Attr(name=sym.name, exp=ir, attr=sym.name, ctx=c)
        return ir

    def _collect_sources(self, copies, defs):
        def _find_root_def(qsym, copy_qsym):
            if qsym[-1] in defs:
                assert env.origin_registry.sym_origin_of(copy_qsym[-1])
                return {qsym[-1]}
            elif env.origin_registry.sym_origin_of(qsym[-1]) and self.qsym_ancestor(qsym) in copy_sources:
                return copy_sources[self.qsym_ancestor(qsym)]
            return None

        if not defs:
            return None
        copy_sources = defaultdict(set)
        worklist = deque()
        for copy_qsym, stm in copies.items():
            if isinstance(stm, Move) and isinstance(stm.src, IrVariable):
                src_qsym = qualified_symbols(stm.src, self.scope)
                worklist.append((src_qsym, copy_qsym))
            elif isinstance(stm, (Phi, UPhi, LPhi)):
                for arg in stm.args:
                    if isinstance(arg, IrVariable):
                        arg_qsym = qualified_symbols(arg, self.scope)
                        worklist.append((arg_qsym, copy_qsym))
        # Process worklist with stall detection: if a full pass through
        # the worklist makes no progress, the remaining items form a
        # circular dependency and cannot be resolved.
        progress = True
        while worklist and progress:
            progress = False
            remaining = len(worklist)
            for _ in range(remaining):
                qsym, copy_qsym = worklist.popleft()
                roots = _find_root_def(qsym, copy_qsym)
                if roots is None:
                    worklist.append((qsym, copy_qsym))
                else:
                    copy_sources[self.qsym_ancestor(copy_qsym)] |= roots
                    progress = True
        return copy_sources

    def _transform_obj_access(self):
        self._transform_use(self.obj_copies, self.obj_copy_sources)
        # Build seq_id mapping first so _transform_use uses seq_id names
        self._build_seq_ids()
        self._transform_use(self.seq_copies, self.seq_copy_sources)
        self._finalize_seq_ctor()

    def _find_use_var(self, stm, qsym):
        max_len = 0
        var = None
        for use_var in self.usedef.get_vars_used_at(stm):
            qsym_ = qualified_symbols(use_var, self.scope)
            if len(qsym_) > max_len:
                var = use_var
                max_len = len(qsym_)
        if not var:
            return None
        var_qsym = qualified_symbols(var, self.scope)
        if var_qsym[:-1] == qsym:
            return var
        return None

    def _find_def_var(self, stm, qsym):
        max_len = 0
        var = None
        for def_var in self.usedef.get_vars_defined_at(stm):
            qsym_ = qualified_symbols(def_var, self.scope)
            if len(qsym_) > max_len:
                var = def_var
                max_len = len(qsym_)
        if not var:
            return None
        var_qsym = qualified_symbols(var, self.scope)
        if var_qsym[:-1] == qsym:
            return var
        return None

    def _transform_use(self, copies, copy_sources):
        if not copy_sources:
            return
        for copy_qsym, copy_stm in copies.items():
            sources = copy_sources[self.qsym_ancestor(copy_qsym)]
            usestms = self.usedef.get_stms_using(copy_qsym).copy()
            for stm in usestms:
                if not isinstance(stm, (Move, Expr)):
                    continue
                if isinstance(copy_stm, (Phi, UPhi, LPhi)) and isinstance(stm, Move):
                    use_var = self._find_use_var(stm, copy_qsym)
                    if use_var or isinstance(stm.src, MRef) or (isinstance(stm.src, SysCall) and stm.src.name == 'len'):
                        self._add_uphi(stm, sources, copy_qsym)
                    def_var = self._find_def_var(stm, copy_qsym)
                    if def_var:
                        self._add_branch_move(stm, sources, copy_qsym)
                elif isinstance(stm, Expr):
                    self._add_cexpr(stm, sources, copy_qsym)

    def _add_uphi(self, mv_stm, sources, copy_qsym):
        insert_idx = self.scope.find_block(mv_stm.block).stms.index(mv_stm)
        tmp = self.scope.add_temp()
        var = Temp(name=tmp.name, ctx=Ctx.STORE)
        uphi = UPhi(var=var, block=mv_stm.block, loc=mv_stm.loc or Loc('', 0))
        for src in sources:
            cmp_name = self._src_cmp_name(src)
            c = RelOp(op='Eq',
                      left=self.qsym_to_ir(copy_qsym, Ctx.LOAD),
                      right=Temp(name=cmp_name))
            c_sym = self.scope.add_condition_sym()
            tmp_mv = Move(dst=Temp(name=c_sym.name, ctx=Ctx.STORE), src=c,
                         loc=mv_stm.loc, block=mv_stm.block)
            self.scope.find_block(mv_stm.block).stms.insert(insert_idx, tmp_mv)
            insert_idx += 1
            uphi.ps.append(Temp(name=c_sym.name))
            mv_src = mv_stm.src.model_copy(deep=True)
            mv_src.replace(self.qsym_to_ir(copy_qsym, Ctx.LOAD), Temp(name=src.name))
            uphi.args.append(mv_src)
        self.scope.find_block(mv_stm.block).stms.insert(insert_idx, uphi)
        var_load = Temp(name=tmp.name, ctx=Ctx.LOAD)
        object.__setattr__(mv_stm, 'src', var_load)

    def _add_branch_move(self, mv_stm, sources, copy_qsym):
        blk = self.scope.find_block(mv_stm.block)
        is_exit = self.scope.exit_block is blk
        stm_idx = blk.stms.index(mv_stm)
        csyms = []
        for src in sources:
            cmp_name = self._src_cmp_name(src)
            cond_rhs = RelOp(op='Eq',
                             left=self.qsym_to_ir(copy_qsym, Ctx.LOAD),
                             right=Temp(name=cmp_name))
            csym = self.scope.add_condition_sym()
            mv = Move(dst=Temp(name=csym.name, ctx=Ctx.STORE), src=cond_rhs,
                     loc=mv_stm.loc, block=blk)
            blk.stms.insert(stm_idx, mv)
            csyms.append(csym)
        stm_idx = blk.stms.index(mv_stm)
        for src, csym in zip(sources, csyms):
            mv_copy = mv_stm.model_copy(deep=True)
            object.__setattr__(mv_copy, 'dst', mv_copy.dst.model_copy(update={'exp': Temp(name=src.name, ctx=Ctx.STORE)}))
            new_tail = self._make_branch(Temp(name=csym.name), mv_copy, blk, stm_idx)
            stm_idx = 0
            blk = new_tail
        self.scope.find_block(mv_stm.block).stms.remove(mv_stm)
        if is_exit:
            self.scope.exit_block = blk

    def _make_branch(self, cond, branch_stm, cur_blk, stm_idx):
        branch_blk = Block(self.scope)
        tail_blk = Block(self.scope)
        tail_blk.succs = cur_blk.succs[:]
        tail_blk.succs_loop = cur_blk.succs_loop[:]
        tail_blk.preds = [branch_blk, cur_blk]
        path = cur_blk.path_exp
        if path and not isinstance(path, Const):
            tail_blk.path_exp = path.model_copy(deep=True)
        else:
            tail_blk.path_exp = Const(value=1)
        for succ in cur_blk.succs:
            replace_item(succ.preds, cur_blk, tail_blk)
        cur_blk.succs = [branch_blk, tail_blk]
        branch_blk.preds = [cur_blk]
        branch_blk.succs = [tail_blk]
        if path and not isinstance(path, Const):
            branch_blk.path_exp = RelOp(op='And', left=cond.model_copy(deep=True),
                                        right=path.model_copy(deep=True))
        else:
            branch_blk.path_exp = cond.model_copy(deep=True)
        # Split stms
        for stm in cur_blk.stms[stm_idx:]:
            object.__setattr__(stm, 'block', tail_blk.bid)
            tail_blk.stms.append(stm)
        cur_blk.stms = cur_blk.stms[:stm_idx]

        cj = CJump(exp=cond, true=branch_blk.bid, false=tail_blk.bid,
                   loc=branch_stm.loc, block=cur_blk.bid)
        cur_blk.stms.append(cj)

        object.__setattr__(branch_stm, 'block', branch_blk.bid)
        branch_blk.stms.append(branch_stm)
        jmp = Jump(target=tail_blk.bid, loc=branch_stm.loc, block=branch_blk.bid)
        branch_blk.stms.append(jmp)
        return tail_blk

    def _add_cexpr(self, expr, sources, copy_qsym):
        insert_idx = self.scope.find_block(expr.block).stms.index(expr)
        for src in sources:
            expr_copy = expr.model_copy(deep=True)
            if isinstance(expr_copy.exp, MStore):
                object.__setattr__(expr_copy, 'exp', expr_copy.exp.model_copy(update={'mem': Temp(name=src.name)}))
            else:
                raise NotImplementedError
            cmp_name = self._src_cmp_name(src)
            c = RelOp(op='Eq',
                      left=self.qsym_to_ir(copy_qsym, Ctx.LOAD),
                      right=Temp(name=cmp_name))
            cexpr = CExpr(cond=c, exp=expr_copy.exp, loc=expr_copy.loc,
                         block=expr.block)
            self.scope.find_block(expr.block).stms.insert(insert_idx, cexpr)
        self.scope.find_block(expr.block).stms.remove(expr)

    def _build_seq_ids(self):
        """Create seq_id symbols and MOVEs, build seq_id_map for _transform_use."""
        for seq_sym in self.seq_defs:
            defstms = self.usedef.get_stms_defining(seq_sym)
            defstm = list(defstms)[0]
            assert isinstance(defstm.src, Array)

            seq_id = self.scope.add_sym(f'{seq_sym.name}{seq_sym.id}__id', tags=set(), typ=Type.int(16))
            env.seq_id_to_array[seq_id.id] = defstm.src
            mv = Move(dst=Temp(name=seq_id.name, ctx=Ctx.STORE),
                     src=Const(value=seq_id.id),
                     loc=defstm.loc, block=defstm.block)
            idx = self.scope.find_block(defstm.block).stms.index(defstm)
            self.scope.find_block(defstm.block).stms.insert(idx, mv)
            self.seq_id_map[seq_sym.name] = seq_id.name

            usestms = self.usedef.get_stms_using(seq_sym)
            for usestm in usestms:
                if isinstance(usestm, Move) and not isinstance(usestm.src, (MRef, SysCall)):
                    usestm.replace(Temp(name=seq_sym.name), Temp(name=seq_id.name))
                elif isinstance(usestm, CMove):
                    cond_vars = usestm.cond.find_vars((seq_sym.name,))
                    for v in cond_vars:
                        usestm.cond.replace(v, Temp(name=seq_id.name))
                elif isinstance(usestm, CExpr):
                    cond_vars = usestm.cond.find_vars((seq_sym.name,))
                    for v in cond_vars:
                        usestm.cond.replace(v, Temp(name=seq_id.name))
                elif isinstance(usestm, (LPhi, Phi)):
                    usestm.replace(Temp(name=seq_sym.name), Temp(name=seq_id.name))

    def _finalize_seq_ctor(self):
        """Change copy variable types to int16."""
        for seq_sym in self.seq_copies.keys():
            seq_sym[-1].typ = Type.int(16)
