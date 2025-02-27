﻿from collections import defaultdict, deque
from .cfgopt import merge_path_exp, rel_and_exp
from .varreplacer import VarReplacer
from .tuple import TupleTransformer
from ..ir import *
from ..irhelper import qualified_symbols
from ..types.type import Type
from ..types import typehelper
from ..analysis.dominator import DominatorTreeBuilder, DominanceFrontierBuilder
from ..analysis.usedef import UseDefDetector
from ...common.env import env
from ...common.utils import replace_item

from logging import getLogger
logger = getLogger(__name__)


class SSATransformerBase(object):
    def __init__(self):
        pass

    def process(self, scope):
        if scope.is_class() or scope.is_namespace():
            return
        self.scope = scope
        self.dominance_frontier = {}
        self.usedef = scope.usedef
        self.phis = []

        self._compute_dominance_frontier()
        self._insert_phi()
        self._rename()

        self._remove_useless_phi()
        self._insert_predicate()
        self._find_loop_phi()
        self._deal_with_return_phi()

    def _sort_phi(self, blk):
        phis = blk.collect_stms(PHI)
        if len(phis) == 1:
            return
        for phi in phis:
            blk.stms.remove(phi)

        phis = sorted(phis, key=lambda p: qualified_symbols(p.var, self.scope), reverse=True)
        for phi in phis:
            blk.insert_stm(0, phi)

    def _insert_phi(self):
        phi_symbols = defaultdict(list)
        dfs = set()
        for qsym, def_blocks in self.usedef.get_qsym_block_dict_items():
            assert isinstance(qsym, tuple)
            if not self._need_rename(qsym[-1], qsym):
                continue
            while def_blocks:
                def_block = def_blocks.pop()
                if def_block not in self.dominance_frontier:
                    continue
                for df in self.dominance_frontier[def_block]:
                    logger.log(0, 'DF of ' + def_block.name + ' = ' + df.name)
                    if qsym in phi_symbols[df]:
                        continue
                    phi_symbols[df].append(qsym)
                    #insert phi to df
                    var = self._qsym_to_var(qsym, Ctx.STORE)
                    phi = self._new_phi(var, df)
                    df.insert_stm(0, phi)
                    #The phi has the definintion of the variable
                    #so we must add the phi to the df_blocks if needed
                    if qsym not in self.usedef.get_qsyms_defined_at(df):
                        def_blocks.add(df)
                    #this must call after the above checking
                    self._add_phi_var_to_usedef(var, phi)
                    self.phis.append(phi)
                    dfs.add(df)
        # In objectssa, the following code is important to make
        # hierarchical PHI definitions in the proper order.
        for df in dfs:
            self._sort_phi(df)

    def _new_phi(self, var, df):
        phi = PHI(var)
        phi.block = df
        phi.args = [CONST(None)] * len(df.preds)
        sym = qualified_symbols(var, self.scope)[-1]
        defs = self.scope.usedef.get_stms_defining(sym)
        for d in defs:
            if d.block is df.preds[0]:
                phi.loc = d.loc
                break
        return phi

    def _add_phi_var_to_usedef(self, var, phi, is_tail_attr=True):
        if is_tail_attr:
            self.usedef.add_var_def(self.scope, var, phi)
            if var.is_a(ATTR):
                self._add_phi_var_to_usedef(var.exp, phi, is_tail_attr=False)
        else:
            self.usedef.add_var_use(self.scope, var, phi)

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
            # key = var.qualified_symbol
            qcount[key] = 0
            qstack[key] = [(0, None)]

        self.new_syms = set()
        self._rename_rec(self.scope.entry_block, qcount, qstack)

        for var, version in self.new_syms:
            assert isinstance(var, IRVariable)
            qsyms = qualified_symbols(var, self.scope)
            if self._need_rename(qsyms[-1], qsyms):
                new_name = var.name + '#' + str(version)
                var_sym = qsyms[-1]
                new_sym = var_sym.scope.inherit_sym(var_sym, new_name)
                logger.debug(str(new_sym) + ' ancestor is ' + str(var_sym))
                var.name = new_name

    def _rename_rec(self, block, count, stack):
        for stm in block.stms:
            if not stm.is_a(PHI):
                for use in self.usedef.get_vars_used_at(stm):
                    assert isinstance(use, IRVariable)
                    qsym = qualified_symbols(use, self.scope)
                    key = qsym
                    i, _ = stack[key][-1]
                    self._add_new_sym(use, i)

                    use_t = qsym[-1].typ
                    for expr_t in typehelper.find_expr(use_t):
                        expr = expr_t.expr
                        vs = expr.find_irs(IRVariable)
                        for v in vs:
                            key = qualified_symbols(v, self.scope)
                            if all([isinstance(k, Symbol) for k in key]):
                                if self._need_rename(key[-1], key):
                                    i, _ = stack[key][-1]
                                    self._add_new_sym(v, i)
            #this loop includes PHI
            for d in self.usedef.get_vars_defined_at(stm):
                #print(stm, d)
                assert isinstance(d, IRVariable)
                key = qualified_symbols(d, self.scope)
                if self._need_rename(key[-1], key):
                    logger.debug('count up ' + str(d) + ' ' + str(stm))
                    count[key] += 1
                i = count[key]
                stack[key].append((i, d))
                self._add_new_sym(d, i)
                if stm.is_a(PHI) and d.is_a(ATTR):
                    self._add_new_sym_rest(d.exp, stack)

                d_t = key[-1].typ
                for expr_t in typehelper.find_expr(d_t):
                    expr = expr_t.expr
                    vs = expr.find_irs(IRVariable)
                    for v in vs:
                        key = qualified_symbols(v, self.scope)
                        if all([isinstance(k, Symbol) for k in key]):
                            if self._need_rename(key[-1], key):
                                i, _ = stack[key][-1]
                                self._add_new_sym(v, i)
        #into successors
        for succ in block.succs:
            phis = [phi for phi in self.phis if phi.block is succ]
            for phi in phis:
                self._add_new_phi_arg(phi, phi.var, stack, block)

        for c in self.tree.get_children_of(block):
            self._rename_rec(c, count, stack)
        for stm in block.stms:
            for d in self.usedef.get_vars_defined_at(stm):
                key = qualified_symbols(d, self.scope)
                if key in stack and stack[key]:
                    stack[key].pop()

    def _add_new_phi_arg(self, phi, var, stack, block, is_tail_attr=True):
        key = qualified_symbols(var, self.scope)
        i, v = stack[key][-1]
        if is_tail_attr:
            if i > 0:
                var = var.clone(ctx=Ctx.LOAD)
                if 1 == phi.block.preds.count(block):
                    idx = phi.block.preds.index(block)
                    phi.args[idx] = var
                    self._add_new_sym(var, i)
                else:
                    for idx, pred in enumerate(phi.block.preds):
                        if pred is not block:
                            continue
                        phi.args[idx] = var
                        self._add_new_sym(var, i)
        else:
            self._add_new_sym(var, i)

        if var.is_a(ATTR):
            self._add_new_phi_arg(phi, var.exp, stack, block, is_tail_attr=False)

    def _need_rename(self, sym, qsym):
        return False

    def _add_new_sym(self, var, version):
        assert isinstance(var, IRVariable)
        qsym = qualified_symbols(var, self.scope)
        if self._need_rename(qsym[-1], qsym):
            self.new_syms.add((var, version))

    def _add_new_sym_rest(self, var, stack):
        assert isinstance(var, IRVariable)
        key = qualified_symbols(var, self.scope)
        i, _ = stack[key][-1]
        self.new_syms.add((var, i))
        if isinstance(var, ATTR):
            self._add_new_sym_rest(var.exp, stack)

    # TODO: qsym2var in irhelper.py
    def _qsym_to_var(self, qsym, ctx):
        if len(qsym) == 1:
            return TEMP(qsym[0].name, ctx)
        else:
            exp = self._qsym_to_var(qsym[:-1], Ctx.LOAD)
            return ATTR(exp, qsym[-1], ctx)

    def dump_df(self):
        for node, dfs in sorted(self.dominance_frontier.items(), key=lambda n: n[0].name):
            logger.debug('DF of ' + node.name + ' is ...' + ', '.join([df.name for df in dfs]))

    def _compute_dominance_frontier(self):
        dtree_builder = DominatorTreeBuilder(self.scope)
        tree = dtree_builder.process()
        tree.dump()
        self.tree = tree

        first_block = self.scope.entry_block
        df_builder = DominanceFrontierBuilder()
        self.dominance_frontier = df_builder.process(first_block, tree)

    def _remove_useless_phi(self):
        udd = UseDefDetector()
        udd.process(self.scope)
        usedef = self.scope.usedef

        def get_arg_name_if_same(phi):
            names = [arg.name for arg in phi.args
                    if arg and
                        isinstance(arg, IRVariable) and
                        arg.name != phi.var.name]
            if names and all(names[0] == s for s in names):
                return names[0]
            else:
                return None
        worklist = deque(self.phis)
        while worklist:
            phi = worklist.popleft()
            if not phi.args:
                self._remove_phi(phi, usedef)
                continue
            var_sym = qualified_symbols(phi.var, self.scope)[-1]
            usestms = usedef.get_stms_using(var_sym)
            if not usestms:
                self._remove_phi(phi, usedef)
                for a in [a for a in phi.args if a and a.is_a(TEMP)]:
                    a_sym = qualified_symbols(a, self.scope)[-1]
                    for defphi in [defstm for defstm in usedef.get_stms_defining(a_sym) if defstm.is_a(PHI)]:
                        worklist.append(defphi)
                continue
            name = get_arg_name_if_same(phi)
            if name:
                replace_var = phi.var.clone(ctx=Ctx.LOAD)
                replace_var.name = name
                replaces = VarReplacer.replace_uses(self.scope, phi.var, replace_var)
                for rep in replaces:
                    if rep.is_a(PHI):
                        worklist.append(rep)
                    usedef.remove_use(self.scope, phi.var, rep)
                    usedef.add_use(self.scope, replace_var, rep)
                self._remove_phi(phi, usedef)

    def _remove_phi(self, phi, usedef):
        logger.debug('remove ' + str(phi))
        if phi in phi.block.stms:
            phi.block.stms.remove(phi)
            usedef.remove_stm(self.scope, phi)
            # self.scope.del_sym(phi.var.symbol.name)

    def _insert_predicate(self):
        for blk in self.scope.traverse_blocks():
            phis = [phi for phi in self.phis if phi.block is blk]
            if not phis:
                continue
            phi_predicates = []
            dup_counts = defaultdict(int)
            for pred in blk.preds:
                if len(pred.succs) == 1:
                    p = pred.path_exp if pred.path_exp else CONST(1)
                else:
                    if pred.succs.count(blk) == 1:
                        p = merge_path_exp(pred, blk)
                    else:
                        dup_count = dup_counts[pred]
                        dup_counts[pred] += 1
                        jump = pred.stms[-1]
                        targets = [(idx, target) for idx, target in enumerate(jump.targets)
                                   if target is blk]
                        for idx, target in targets:
                            if dup_count == 0:
                                p = rel_and_exp(pred.path_exp, jump.conds[idx])
                                break
                            else:
                                dup_count -= 1
                phi_predicates.append(p)

            for phi in phis:
                phi.ps = phi_predicates[:]
                assert len(phi.ps) == len(phi.args)

    def _find_loop_phi(self):
        for phi in self.phis[:]:
            blk = phi.block
            if not blk.preds_loop:
                continue
            lphi = LPHI.from_phi(phi)
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
                    if a.is_a(CONST):
                        print(a)
                    if a.is_a(IRVariable):
                        a_sym = qualified_symbols(a, self.scope)[-1]
                        assert isinstance(a_sym, Symbol)
                        a_sym.del_tag('return')
                    #new_name = 'ret' + a.symbol.name.split('#')[1]
                    # while new_name in self.scope.symbols:
                    #    new_name = '_' + new_name
                    # a.symbol.name = new_name


class ScalarSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def _need_rename(self, sym, qsym):
        if (sym.is_condition() or
                sym.is_param() or
                sym.is_static() or
                #sym.is_flattened() or
                sym.typ.name in ['function', 'class', 'object', 'tuple', 'port']):
            return False
        if len(qsym) > 1:
            return False
        defstms = self.usedef.get_stms_defining(qsym)
        if len(defstms) <= 1:
            return False
        return True


class TupleSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        if scope.is_class() or scope.is_namespace():
            return
        super().process(scope)
        UseDefDetector().process(scope)
        TupleTransformer().process(scope)
        UseDefDetector().process(scope)
        self._process_use_phi()

    def _process_use_phi(self):
        usedef = self.scope.usedef
        for phi in self.phis:
            qsym = qualified_symbols(phi.var, self.scope)
            uses = usedef.get_stms_using(qsym)
            for use in uses:
                self._insert_use_phi(phi, use)

    def _insert_use_phi(self, phi, use_stm):
        insert_idx = use_stm.block.stms.index(use_stm)
        qname = phi.var.qualified_name
        if use_stm.is_a(MOVE):
            src_use_vars = [ir for ir in use_stm.src.find_vars(qname)]
            dst_use_vars = [ir for ir in use_stm.dst.find_vars(qname)]
            if src_use_vars:
                use_var = src_use_vars[0]
                uphi = UPHI(use_stm.dst.clone())
                uphi.ps = phi.ps[:]
                for arg in phi.args:
                    src = use_stm.src.clone()
                    src.replace(use_var, arg.clone())
                    uphi.args.append(src)
                use_stm.block.insert_stm(insert_idx, uphi)
            else:
                assert dst_use_vars
                use_var = dst_use_vars[0]
                for p, arg in zip(phi.ps, phi.args):
                    dst = use_stm.dst.clone()
                    dst.replace(use_var, arg.clone())
                    assert False, 'CMOVE'
                    cmov = CMOVE(p.clone(), dst, use_stm.src.clone())
                    use_stm.block.insert_stm(insert_idx, cmov)
            use_stm.block.stms.remove(use_stm)
        elif use_stm.is_a(EXPR):
            use_vars = [ir for ir in use_stm.exp.find_vars(qname)]
            assert use_vars
            use_var = use_vars[0]
            for p, arg in zip(phi.ps, phi.args):
                exp = use_stm.exp.clone()
                exp.replace(use_var, arg.clone())
                cexp = CEXPR(p.clone(), exp)
                use_stm.block.insert_stm(insert_idx, cexp)
            use_stm.block.stms.remove(use_stm)
        else:
            assert False

    def _need_rename(self, sym, qsym):
        if sym.scope.is_namespace() or sym.scope.is_class():
            return False
        sym_t = sym.typ
        return sym_t.is_tuple() and not sym.is_param()


class ListSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def _need_rename(self, sym, qsym):
        if sym.scope.is_namespace() or sym.scope.is_class():
            return False
        sym_t = sym.typ
        return sym_t.is_list() and not sym.is_param()


class ObjectSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

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
