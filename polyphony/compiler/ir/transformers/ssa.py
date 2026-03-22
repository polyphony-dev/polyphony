"""SSA transformers using new IR (ir.py).

Converts IR to SSA form by inserting PHI nodes, renaming variables,
and handling loop PHIs and predicates.
"""
from collections import defaultdict, deque
from .cfgopt import can_merge_synth_params
from ..ir import (
    Ir, IrExp, IrStm, IrVariable, IrNameExp, Loc,
    Const, Temp, Attr, Move, Expr, CExpr, Jump, CJump, MCJump,
    Phi, UPhi, LPhi, Call, SysCall, New,
    Ctx,
)
from ..irhelper import qualified_symbols, qsym2var
from ..irvisitor import IrVisitor
from ..types.type import Type
from ..types import typehelper
from ..analysis.dominator import DominatorTreeBuilder, DominanceFrontierBuilder
from ..analysis.usedef import UseDefDetector, UseDefUpdater
from ..analysis.usedef import UseDefItem
from .varreplacer import VarReplacer
from ..symbol import Symbol
from ...common.env import env
from ...common.utils import replace_item
from logging import getLogger
logger = getLogger(__name__)


def _merge_path_exp(pred, blk, idx_hint=-1):
    """Compute path expression for reaching blk from pred (new IR version)."""
    from ..ir import RelOp, UnOp
    jump = pred.stms[-1] if pred.stms else None
    exp = pred.path_exp
    if isinstance(jump, CJump):
        if blk.bid == jump.true:
            exp = _rel_and_exp(pred.path_exp, jump.exp)
        elif blk.bid == jump.false:
            exp = _rel_and_exp(pred.path_exp, UnOp(op='Not', exp=jump.exp))
    elif isinstance(jump, MCJump):
        if blk.bid in jump.targets:
            if 1 == jump.targets.count(blk.bid):
                idx = jump.targets.index(blk.bid)
                exp = _rel_and_exp(pred.path_exp, jump.conds[idx])
            elif idx_hint >= 0:
                exp = _rel_and_exp(pred.path_exp, jump.conds[idx_hint])
            else:
                from ..ir import RelOp
                indices = [i for i, t in enumerate(jump.targets) if t == blk.bid]
                exp = _rel_and_exp(pred.path_exp, jump.conds[indices[0]])
                for idx in indices[1:]:
                    rexp = _rel_and_exp(pred.path_exp, jump.conds[idx])
                    exp = RelOp(op='Or', left=exp, right=rexp)
    return exp


def _rel_and_exp(exp1, exp2):
    from ..ir import RelOp
    from ..irhelper import reduce_relexp
    if exp1 is None:
        return exp2
    if exp2 is None:
        return exp1
    exp1 = reduce_relexp(exp1)
    exp2 = reduce_relexp(exp2)
    if isinstance(exp1, Const) and exp1.value:
        return exp2
    if isinstance(exp2, Const) and exp2.value:
        return exp1
    return RelOp(op='And', left=exp1, right=exp2)


class SSATransformerBase(object):
    def __init__(self):
        pass

    def process(self, scope):
        if scope.is_class() or scope.is_namespace():
            return
        self.scope = scope
        self.dominance_frontier = {}
        self.usedef = UseDefDetector().process(scope)
        self.phis = []

        self._compute_dominance_frontier()
        self._insert_phi()
        self._rename()

        self._remove_useless_phi()
        self._insert_predicate()
        self._find_loop_phi()
        self._deal_with_return_phi()

    def _sort_phi(self, blk):
        phis = [stm for stm in blk.stms if type(stm) is Phi]
        if len(phis) <= 1:
            return
        for phi in phis:
            blk.stms.remove(phi)
        phis = sorted(phis, key=lambda p: qualified_symbols(p.var, self.scope), reverse=True)
        for phi in phis:
            if phi.block != blk.bid:
                phi = phi.model_copy(update={'block': blk.bid})
            blk.stms.insert(0, phi)

    def _insert_phi(self):
        phi_symbols = defaultdict(list)
        dfs = set()
        for qsym, def_block_bids in self.usedef.get_qsym_block_dict_items():
            assert isinstance(qsym, tuple)
            if not self._need_rename(qsym[-1], qsym):
                continue
            # Convert bid strings to Block objects for dominance frontier lookup
            def_blocks = set(self.scope.find_block(bid) for bid in def_block_bids if bid in self.scope.block_map)
            while def_blocks:
                def_block = def_blocks.pop()
                if def_block not in self.dominance_frontier:
                    continue
                for df in self.dominance_frontier[def_block]:
                    if qsym in phi_symbols[df]:
                        continue
                    phi_symbols[df].append(qsym)
                    var = self._qsym_to_var(qsym, Ctx.STORE)
                    phi = self._new_phi(var, df)
                    if phi.block != df.bid:
                        phi = phi.model_copy(update={'block': df.bid})
                    df.stms.insert(0, phi)
                    if qsym not in self.usedef.get_qsyms_defined_at(df):
                        def_blocks.add(df)
                    self._add_phi_var_to_usedef(var, phi)
                    self.phis.append(phi)
                    dfs.add(df)
        for df in dfs:
            self._sort_phi(df)

    def _new_phi(self, var, df):
        phi = Phi(var=var, args=tuple(Const(value=None) for _ in df.preds))
        sym = qualified_symbols(var, self.scope)[-1]
        assert isinstance(sym, Symbol)
        defs = self.usedef.get_stms_defining(sym)
        for d in defs:
            if d.block == df.preds[0].bid:
                phi = phi.model_copy(update={'loc': d.loc})
                break
        return phi

    def _add_phi_var_to_usedef(self, var, phi, is_tail_attr=True):
        qsyms = qualified_symbols(var, self.scope)
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, phi, phi.block)
        if is_tail_attr:
            self.usedef._def_sym2[sym].add(item)
            self.usedef._def_qsym2[qsyms].add(item)
            self.usedef._def_var2[var].add(item)
            self.usedef._def_stm2[phi].add(item)
            self.usedef._def_blk2[phi.block].add(item)
            if isinstance(var, Attr):
                self._add_phi_var_to_usedef(var.exp, phi, is_tail_attr=False)
        else:
            self.usedef._use_sym2[sym].add(item)
            self.usedef._use_qsym2[qsyms].add(item)
            self.usedef._use_var2[var].add(item)
            self.usedef._use_stm2[phi].add(item)
            self.usedef._use_blk2[phi.block].add(item)

    def _rename(self):
        qcount = {}
        qstack = {}
        using_vars = set()
        for blk in self.scope.traverse_blocks():
            for var in self.usedef.get_vars_defined_at(blk):
                using_vars.add(var)
            for var in self.usedef.get_vars_used_at(blk):
                using_vars.add(var)
        for var in using_vars:
            key = qualified_symbols(var, self.scope)
            qcount[key] = 0
            qstack[key] = [(0, None)]

        self.new_syms = []
        self._rename_rec(self.scope.entry_block, qcount, qstack)

        # Build rename_map: id(old_var) -> new_var with versioned name
        rename_map: dict[int, 'IrVariable'] = {}
        for var, version in self.new_syms:
            assert isinstance(var, IrVariable)
            qsyms = qualified_symbols(var, self.scope)
            if self._need_rename(qsyms[-1], qsyms):
                new_name = var.name + '#' + str(version)
                var_sym = qsyms[-1]
                assert isinstance(var_sym, Symbol)
                var_sym.scope.inherit_sym(var_sym, new_name)
                updates: dict = {'name': new_name}
                if isinstance(var, Attr):
                    updates['attr'] = new_name
                rename_map[id(var)] = var.model_copy(update=updates)

        # Apply batch substitution across all stmts; update self.phis for changed phi stmts
        old_phi_ids = {id(p): i for i, p in enumerate(self.phis)}
        for blk in self.scope.traverse_blocks():
            for stm in list(blk.stms):
                new_stm = stm.subst_by_id(rename_map)
                if new_stm is not stm:
                    blk.replace_stm(stm, new_stm)
                    if id(stm) in old_phi_ids:
                        self.phis[old_phi_ids[id(stm)]] = new_stm

        # Rebuild usedef from scratch — new var objects are now in the IR
        self.usedef = UseDefDetector().process(self.scope)

    def _rename_rec(self, block, count, stack):
        for stm in block.stms:
            if type(stm) is not Phi:
                for use in self.usedef.get_vars_used_at(stm):
                    assert isinstance(use, IrVariable)
                    qsym = qualified_symbols(use, self.scope)
                    key = qsym
                    if key not in stack or not stack[key]:
                        continue
                    i, _ = stack[key][-1]
                    self._add_new_sym(use, i)

                    use_t_sym = qsym[-1]
                    assert isinstance(use_t_sym, Symbol)
                    use_t = use_t_sym.typ
                    for expr_t in typehelper.find_expr(use_t):
                        expr = expr_t.expr
                        vs = expr.find_irs(IrVariable)
                        for v in vs:
                            key = qualified_symbols(v, self.scope)
                            if all(isinstance(k, Symbol) for k in key):
                                if self._need_rename(key[-1], key):
                                    i, _ = stack[key][-1]
                                    self._add_new_sym(v, i)
            for d in self.usedef.get_vars_defined_at(stm):
                assert isinstance(d, IrVariable)
                key = qualified_symbols(d, self.scope)
                if self._need_rename(key[-1], key):
                    count[key] += 1
                i = count[key]
                stack[key].append((i, d))
                self._add_new_sym(d, i)
                if isinstance(stm, Phi) and isinstance(d, Attr):
                    self._add_new_sym_rest(d.exp, stack)

                d_t_sym = key[-1]
                assert isinstance(d_t_sym, Symbol)
                d_t = d_t_sym.typ
                for expr_t in typehelper.find_expr(d_t):
                    expr = expr_t.expr
                    vs = expr.find_irs(IrVariable)
                    for v in vs:
                        key = qualified_symbols(v, self.scope)
                        if all(isinstance(k, Symbol) for k in key):
                            if self._need_rename(key[-1], key):
                                i, _ = stack[key][-1]
                                self._add_new_sym(v, i)
        for succ in block.succs:
            phis = [phi for phi in self.phis if phi.block == succ.bid]
            for phi in phis:
                self._add_new_phi_arg(phi, phi.var, stack, block)

        for c in self.tree.get_children_of(block):
            self._rename_rec(c, count, stack)
        for stm in block.stms:
            for d in self.usedef.get_vars_defined_at(stm):
                key = qualified_symbols(d, self.scope)
                if key in stack and stack[key]:
                    stack[key].pop()

    def _update_phi(self, phi, new_phi):
        """Replace phi with new_phi in its block, update self.phis and usedef."""
        phi_blk = self.scope.find_block(phi.block)
        phi_blk.replace_stm(phi, new_phi)
        self.usedef.replace_stm(phi, new_phi)
        idx = next(i for i, p in enumerate(self.phis) if p is phi)
        self.phis[idx] = new_phi

    def _add_new_phi_arg(self, phi, var, stack, block, is_tail_attr=True):
        key = qualified_symbols(var, self.scope)
        i, v = stack[key][-1]
        if is_tail_attr:
            if i > 0:
                var = var.clone(ctx=Ctx.LOAD)
                phi_blk = self.scope.find_block(phi.block)
                if 1 == phi_blk.preds.count(block):
                    idx = phi_blk.preds.index(block)
                    new_phi = phi.model_copy(update={'args': phi.args[:idx] + (var,) + phi.args[idx + 1:]})
                    self._update_phi(phi, new_phi)
                    self._add_new_sym(var, i)
                else:
                    current_phi = phi
                    for idx, pred in enumerate(phi_blk.preds):
                        if pred is not block:
                            continue
                        new_phi = current_phi.model_copy(update={'args': current_phi.args[:idx] + (var,) + current_phi.args[idx + 1:]})
                        self._update_phi(current_phi, new_phi)
                        current_phi = new_phi
                        self._add_new_sym(var, i)
        else:
            self._add_new_sym(var, i)

        if isinstance(var, Attr):
            self._add_new_phi_arg(phi, var.exp, stack, block, is_tail_attr=False)

    def _need_rename(self, sym, qsym) -> bool:
        return False

    def _add_new_sym(self, var, version):
        assert isinstance(var, IrVariable)
        qsym = qualified_symbols(var, self.scope)
        if self._need_rename(qsym[-1], qsym):
            # Use id-based dedup to match old SSA's set behavior.
            # Same (var object, version) should only appear once.
            if not any(v is var and ver == version for v, ver in self.new_syms):
                self.new_syms.append((var, version))

    def _add_new_sym_rest(self, var, stack):
        assert isinstance(var, IrVariable)
        key = qualified_symbols(var, self.scope)
        i, _ = stack[key][-1]
        if not any(v is var and ver == i for v, ver in self.new_syms):
            self.new_syms.append((var, i))
        if isinstance(var, Attr):
            self._add_new_sym_rest(var.exp, stack)

    def _qsym_to_var(self, qsym, ctx):
        if len(qsym) == 1:
            return Temp(name=qsym[0].name, ctx=ctx)
        else:
            exp = self._qsym_to_var(qsym[:-1], Ctx.LOAD)
            return Attr(name=qsym[-1].name, exp=exp, attr=qsym[-1].name, ctx=ctx)

    def _compute_dominance_frontier(self):
        dtree_builder = DominatorTreeBuilder(self.scope)
        tree = dtree_builder.process()
        self.tree = tree

        first_block = self.scope.entry_block
        df_builder = DominanceFrontierBuilder()
        self.dominance_frontier = df_builder.process(first_block, tree)

    def _remove_useless_phi(self):
        self.usedef = UseDefDetector().process(self.scope)
        usedef = self.usedef

        def get_arg_name_if_same(phi):
            names = [arg.name for arg in phi.args
                    if arg and isinstance(arg, IrVariable) and arg.name != phi.var.name]
            if names and all(names[0] == s for s in names):
                return names[0]
            return None

        worklist = deque(self.phis)
        while worklist:
            phi = worklist.popleft()
            if not phi.args:
                self._remove_phi(phi, usedef)
                continue
            var_sym = qualified_symbols(phi.var, self.scope)[-1]
            assert isinstance(var_sym, Symbol)
            usestms = usedef.get_stms_using(var_sym)
            if not usestms:
                self._remove_phi(phi, usedef)
                for a in [a for a in phi.args if a and isinstance(a, Temp)]:
                    a_sym = qualified_symbols(a, self.scope)[-1]
                    assert isinstance(a_sym, Symbol)
                    for defphi in [defstm for defstm in usedef.get_stms_defining(a_sym) if isinstance(defstm, Phi)]:
                        worklist.append(defphi)
                continue
            name = get_arg_name_if_same(phi)
            if name:
                replace_var = phi.var.model_copy(update={'ctx': Ctx.LOAD, 'name': name})
                replaces = VarReplacer.replace_uses(self.scope, phi.var, replace_var, self.usedef)
                for rep in replaces:
                    if isinstance(rep, Phi):
                        worklist.append(rep)
                    # Update usedef: remove old var use, add new var use
                    self._update_usedef_replace(usedef, phi.var, replace_var, rep)
                self._remove_phi(phi, usedef)

    def _update_usedef_replace(self, usedef, old_var, new_var, stm):
        """Remove old_var use and add new_var use for stm in usedef."""
        old_qsyms = qualified_symbols(old_var, self.scope)
        old_sym = old_qsyms[-1]
        if isinstance(old_sym, Symbol):
            item = UseDefItem(old_sym, old_qsyms, old_var, stm, stm.block)
            usedef._use_sym2[old_sym].discard(item)
            usedef._use_qsym2[old_qsyms].discard(item)
            usedef._use_var2[old_var].discard(item)
            usedef._use_stm2[stm].discard(item)
            usedef._use_blk2[stm.block].discard(item)
        new_qsyms = qualified_symbols(new_var, self.scope)
        new_sym = new_qsyms[-1]
        if isinstance(new_sym, Symbol):
            item = UseDefItem(new_sym, new_qsyms, new_var, stm, stm.block)
            usedef._use_sym2[new_sym].add(item)
            usedef._use_qsym2[new_qsyms].add(item)
            usedef._use_var2[new_var].add(item)
            usedef._use_stm2[stm].add(item)
            usedef._use_blk2[stm.block].add(item)

    def _remove_phi(self, phi, usedef):
        phi_blk = self.scope.find_block(phi.block)
        if phi in phi_blk.stms:
            phi_blk.stms.remove(phi)
            # Remove all uses/defs of this phi from usedef
            for var in list(usedef.get_vars_used_at(phi)):
                qsyms = qualified_symbols(var, self.scope)
                sym = qsyms[-1]
                if isinstance(sym, Symbol):
                    item = UseDefItem(sym, qsyms, var, phi, phi.block)
                    usedef._use_sym2[sym].discard(item)
                    usedef._use_qsym2[qsyms].discard(item)
                    usedef._use_var2[var].discard(item)
                    usedef._use_stm2[phi].discard(item)
                    usedef._use_blk2[phi.block].discard(item)
            for var in list(usedef.get_vars_defined_at(phi)):
                qsyms = qualified_symbols(var, self.scope)
                sym = qsyms[-1]
                if isinstance(sym, Symbol):
                    item = UseDefItem(sym, qsyms, var, phi, phi.block)
                    usedef._def_sym2[sym].discard(item)
                    usedef._def_qsym2[qsyms].discard(item)
                    usedef._def_var2[var].discard(item)
                    usedef._def_stm2[phi].discard(item)
                    usedef._def_blk2[phi.block].discard(item)

    def _insert_predicate(self):
        for blk in self.scope.traverse_blocks():
            phis = [phi for phi in self.phis if phi.block == blk.bid]
            if not phis:
                continue
            phi_predicates = []
            dup_counts = defaultdict(int)
            p = Const(value=1)
            for pred in blk.preds:
                if len(pred.succs) == 1:
                    path_exp = pred.path_exp
                    p = path_exp if path_exp else Const(value=1)
                else:
                    if pred.succs.count(blk) == 1:
                        p = _merge_path_exp(pred, blk)
                    else:
                        dup_count = dup_counts[pred]
                        dup_counts[pred] += 1
                        jump = pred.stms[-1]
                        targets = [(idx, target) for idx, target in enumerate(jump.targets)
                                   if target == blk.bid]
                        for idx, target in targets:
                            if dup_count == 0:
                                p = _rel_and_exp(pred.path_exp, jump.conds[idx])
                                break
                            else:
                                dup_count -= 1
                phi_predicates.append(p)

            for phi in phis:
                new_phi = phi.model_copy(update={'ps': tuple(phi_predicates)})
                blk.replace_stm(phi, new_phi)
                phis_idx = next(i for i, p in enumerate(self.phis) if p is phi)
                self.phis[phis_idx] = new_phi
                assert len(new_phi.ps) == len(new_phi.args)

    def _find_loop_phi(self):
        for phi in self.phis[:]:
            blk = self.scope.find_block(phi.block)
            if not blk.preds_loop:
                continue
            lphi = LPhi(var=phi.var.model_copy(deep=True),
                        args=phi.args,
                        ps=tuple(Const(value=1) for _ in phi.ps),
                        block=phi.block, loc=phi.loc)
            replace_item(blk.stms, phi, lphi)
            replace_item(self.phis, phi, lphi)
            var_sym = qualified_symbols(lphi.var, self.scope)[-1]
            assert isinstance(var_sym, Symbol)
            typ = var_sym.typ
            if typ.is_scalar() or typ.is_seq() or typ.is_object():
                var_sym.add_tag('induction')

    def _deal_with_return_phi(self):
        for phi in self.phis:
            var_sym = qualified_symbols(phi.var, self.scope)[-1]
            assert isinstance(var_sym, Symbol)
            if var_sym.is_return():
                for a in phi.args:
                    if isinstance(a, IrVariable):
                        a_sym = qualified_symbols(a, self.scope)[-1]
                        assert isinstance(a_sym, Symbol)
                        a_sym.del_tag('return')


class ScalarSSATransformer(SSATransformerBase):
    def _need_rename(self, sym, qsym):
        if (sym.is_condition() or
                sym.is_param() or
                sym.is_static() or
                sym.typ.name in ['function', 'class', 'object', 'tuple', 'port']):
            return False
        if len(qsym) > 1:
            return False
        defstms = self.usedef.get_stms_defining(qsym)
        if len(defstms) <= 1:
            return False
        return True


class ListSSATransformer(SSATransformerBase):
    def _need_rename(self, sym, qsym):
        if sym.scope.is_namespace() or sym.scope.is_class():
            return False
        sym_t = sym.typ
        return sym_t.is_list() and not sym.is_param()


class ObjectSSATransformer(SSATransformerBase):
    def _need_rename(self, sym, qsym):
        sym_t = sym.typ
        if not sym_t.is_object():
            return False
        if sym.name == env.self_name:
            return False
        if sym.scope.is_module() or sym.scope.is_namespace():
            return False
        if sym.is_param():
            return False
        if sym.is_free():
            return False
        if sym_t.scope and sym_t.scope.is_module():
            return False
        idx = qsym.index(sym)
        if idx > 0:
            if not self._need_rename(qsym[idx - 1], qsym):
                return False
        return True


class TupleSSATransformer(SSATransformerBase):
    def process(self, scope):
        if scope.is_class() or scope.is_namespace():
            return
        super().process(scope)
        from .tuple import TupleTransformer
        TupleTransformer().process(scope)
        self.usedef = UseDefDetector().process(scope)
        self._process_use_phi()

    def _process_use_phi(self):
        usedef = self.usedef
        for phi in self.phis:
            qsym = qualified_symbols(phi.var, self.scope)
            uses = usedef.get_stms_using(qsym)
            for use in uses:
                self._insert_use_phi(phi, use)

    def _insert_use_phi(self, phi, use_stm):
        use_blk = self.scope.find_block(use_stm.block)
        insert_idx = use_blk.stms.index(use_stm)
        qname = phi.var.qualified_name
        if isinstance(use_stm, Move):
            src_use_vars = use_stm.src.find_vars(qname)
            dst_use_vars = use_stm.dst.find_vars(qname)
            if src_use_vars:
                use_var = src_use_vars[0]
                new_args = tuple(use_stm.src.subst(use_var, arg) for arg in phi.args)
                assert isinstance(use_stm.dst, IrVariable)
                uphi = UPhi(var=use_stm.dst.model_copy(deep=True),
                            args=new_args, ps=phi.ps,
                            block=use_stm.block, loc=use_stm.loc or Loc('', 0))
                use_blk.stms.insert(insert_idx, uphi)
            else:
                assert dst_use_vars
                assert False, 'CMOVE path not implemented'
            use_blk.stms.remove(use_stm)
        elif isinstance(use_stm, Expr):
            use_vars = use_stm.exp.find_vars(qname)
            assert use_vars
            use_var = use_vars[0]
            for p, arg in zip(phi.ps, phi.args):
                exp = use_stm.exp.subst(use_var, arg)
                cexp = CExpr(cond=p.model_copy(deep=True), exp=exp,
                             block=use_stm.block, loc=use_stm.loc or Loc('', 0))
                use_blk.stms.insert(insert_idx, cexp)
            use_blk.stms.remove(use_stm)
        else:
            assert False

    def _need_rename(self, sym, qsym):
        if sym.scope.is_namespace() or sym.scope.is_class():
            return False
        sym_t = sym.typ
        return sym_t.is_tuple() and not sym.is_param()
