from collections import defaultdict, deque
from .cfgopt import merge_path_exp, rel_and_exp
from .dominator import DominatorTreeBuilder, DominanceFrontierBuilder
from .env import env
from .symbol import Symbol
from .ir import *
from .tuple import TupleTransformer
from .usedef import UseDefDetector
from .utils import replace_item
from .varreplacer import VarReplacer
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

        phis = sorted(phis, key=lambda p: p.var.qualified_symbol(), reverse=True)
        for phi in phis:
            blk.insert_stm(0, phi)

    def _insert_phi(self):
        phi_symbols = defaultdict(list)
        dfs = set()
        for qsym, def_blocks in self.usedef._def_qsym2blk.items():
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
                    if var.is_a(ATTR):
                        assert qsym[0].typ.is_object()
                        var.attr_scope = qsym[0].typ.get_scope()
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
        phi.args = [None] * len(df.preds)
        phi.lineno = 1
        var.lineno = 1
        return phi

    def _add_phi_var_to_usedef(self, var, phi, is_tail_attr=True):
        if is_tail_attr:
            self.usedef.add_var_def(var, phi)
            if var.is_a(ATTR):
                self._add_phi_var_to_usedef(var.exp, phi, is_tail_attr=False)
        else:
            self.usedef.add_var_use(var, phi)

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
            key = var.qualified_symbol()
            qcount[key] = 0
            qstack[key] = [(0, None)]

        self.new_syms = set()
        self._rename_rec(self.scope.entry_block, qcount, qstack)

        for var, version in self.new_syms:
            assert var.is_a([TEMP, ATTR])
            if self._need_rename(var.symbol(), var.qualified_symbol()):
                new_name = var.symbol().name + '#' + str(version)
                var_sym = var.symbol()
                new_sym = self.scope.inherit_sym(var_sym, new_name)
                logger.debug(str(new_sym) + ' ancestor is ' + str(var.symbol()))
                var.set_symbol(new_sym)

    def _rename_rec(self, block, count, stack):
        for stm in block.stms:
            if not stm.is_a(PHI):
                for use in self.usedef.get_vars_used_at(stm):
                    assert use.is_a([TEMP, ATTR])
                    key = use.qualified_symbol()
                    i, _ = stack[key][-1]
                    self._add_new_sym(use, i)
            #this loop includes PHI
            for d in self.usedef.get_vars_defined_at(stm):
                #print(stm, d)
                assert d.lineno > 0
                assert d.is_a([TEMP, ATTR])
                key = d.qualified_symbol()
                if self._need_rename(d.symbol(), d.qualified_symbol()):
                    logger.debug('count up ' + str(d) + ' ' + str(stm))
                    count[key] += 1
                i = count[key]
                stack[key].append((i, d))
                self._add_new_sym(d, i)
                if stm.is_a(PHI) and d.is_a(ATTR):
                    self._add_new_sym_rest(d.exp, stack)
        #into successors
        for succ in block.succs:
            #collect phi
            phis = succ.collect_stms(PHI)
            for phi in phis:
                self._add_new_phi_arg(phi, phi.var, stack, block)

        for c in self.tree.get_children_of(block):
            self._rename_rec(c, count, stack)
        for stm in block.stms:
            for d in self.usedef.get_vars_defined_at(stm):
                key = d.qualified_symbol()
                if key in stack and stack[key]:
                    stack[key].pop()

    def _add_new_phi_arg(self, phi, var, stack, block, is_tail_attr=True):
        key = var.qualified_symbol()
        i, v = stack[key][-1]
        if is_tail_attr:
            if i > 0:
                var = var.clone()
                var.ctx = Ctx.LOAD
                var.lineno = v.lineno
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
        assert var.is_a([TEMP, ATTR])
        if self._need_rename(var.symbol(), var.qualified_symbol()):
            self.new_syms.add((var, version))

    def _add_new_sym_rest(self, var, stack):
        assert var.is_a([TEMP, ATTR])
        key = var.qualified_symbol()
        i, _ = stack[key][-1]
        self.new_syms.add((var, i))
        if var.is_a(ATTR):
            self._add_new_sym_rest(var.exp, stack)

    def _qsym_to_var(self, qsym, ctx):
        if len(qsym) == 1:
            return TEMP(qsym[0], ctx)
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

        def get_sym_if_having_only_1(phi):
            syms = [arg.symbol() for arg in phi.args if arg and arg.is_a([TEMP, ATTR]) and arg.symbol() is not phi.var.symbol()]
            if syms and all(syms[0] == s for s in syms):
                return syms[0]
            else:
                return None
        worklist = deque()
        for blk in self.scope.traverse_blocks():
            worklist.extend(blk.collect_stms(PHIBase))
        while worklist:
            phi = worklist.popleft()
            if not phi.args:
                self._remove_phi(phi, usedef)
                continue
            usestms = usedef.get_stms_using(phi.var.symbol())
            if not usestms:
                self._remove_phi(phi, usedef)
                for a in [a for a in phi.args if a and a.is_a(TEMP)]:
                    for defphi in [defstm for defstm in usedef.get_stms_defining(a.symbol()) if defstm.is_a(PHI)]:
                        worklist.append(defphi)
                continue
            sym = get_sym_if_having_only_1(phi)
            if sym:
                self._remove_phi(phi, usedef)
                replace_var = phi.var.clone()
                replace_var.set_symbol(sym)
                replace_var.ctx = Ctx.LOAD
                replaces = VarReplacer.replace_uses(phi.var, replace_var, usedef)
                for rep in replaces:
                    if rep.is_a(PHI):
                        worklist.append(rep)
                    usedef.remove_use(phi.var, rep)
                    usedef.add_use(replace_var, rep)

    def _remove_phi(self, phi, usedef):
        logger.debug('remove ' + str(phi))
        if phi in phi.block.stms:
            phi.block.stms.remove(phi)
            for a in phi.args:
                if a:
                    usedef.remove_use(a, phi)
            usedef.remove_var_def(phi.var, phi)

    def _insert_predicate(self):
        for blk in self.scope.traverse_blocks():
            phis = blk.collect_stms(PHI)
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
        for blk in self.scope.traverse_blocks():
            phis = blk.collect_stms(PHI)
            if not phis:
                continue
            if not blk.preds_loop:
                continue
            for phi in phis:
                #if phi.ps[0].is_a(CONST) and phi.ps[0].value:
                lphi = LPHI.from_phi(phi)
                replace_item(blk.stms, phi, lphi)
                if lphi.var.symbol().typ.is_scalar():
                    lphi.var.symbol().add_tag('induction')

    def _deal_with_return_phi(self):
        for blk in self.scope.traverse_blocks():
            phis = blk.collect_stms(PHI)
            for phi in phis:
                if phi.var.symbol().is_return():
                    for a in phi.args:
                        a.symbol().del_tag('return')
                        new_name = 'ret' + a.symbol().name.split('#')[1]
                        while new_name in self.scope.symbols:
                            new_name = '_' + new_name
                        a.symbol().name = new_name


class ScalarSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

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
        for blk in self.scope.traverse_blocks():
            phis = blk.collect_stms(PHI)
            for phi in phis:
                uses = usedef.get_stms_using(phi.var.qualified_symbol())
                for use in uses:
                    self._insert_use_phi(phi, use)

    def _insert_use_phi(self, phi, use_stm):
        insert_idx = use_stm.block.stms.index(use_stm)
        use_mrefs = [ir for ir in use_stm.find_irs(MREF) if ir.mem.symbol().typ.is_tuple()]
        qsym = phi.var.qualified_symbol()

        def replace_attr(mref, qsym, newmem):
            if mref.mem.qualified_symbol() == qsym:
                mref.mem = newmem

        for mref in use_mrefs:
            if mref.mem.qualified_symbol() == qsym:
                tmp = self.scope.add_temp('{}_{}'.format(Symbol.temp_prefix,
                                                         mref.mem.symbol().orig_name()))
                var = TEMP(tmp, Ctx.STORE)
                var.lineno = use_stm.lineno
                uphi = UPHI(var)
                uphi.lineno = use_stm.lineno
                uphi.ps = phi.ps[:]
                for arg in phi.args:
                    argmref = mref.clone()
                    argmref.lineno = use_stm.lineno
                    argmref.mem = arg.clone()
                    uphi.args.append(argmref)
                use_stm.block.insert_stm(insert_idx, uphi)
            var = var.clone()
            var.ctx = Ctx.LOAD
            use_stm.replace(mref, var)
        pass

    def _need_rename(self, sym, qsym):
        if sym.scope.is_namespace() or sym.scope.is_class():
            return False
        return sym.typ.is_tuple() and not sym.is_param()


class ObjectSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        if scope.is_class() or scope.is_namespace():
            return
        super().process(scope)
        self._process_use_phi()

    def _process_use_phi(self):
        usedef = self.scope.usedef
        for blk in self.scope.traverse_blocks():
            phis = blk.collect_stms(PHI)
            for phi in phis:
                uses = usedef.get_stms_using(phi.var.qualified_symbol())
                for use in uses:
                    self._insert_use_phi(phi, use)

    def _insert_use_phi(self, phi, use_stm):
        insert_idx = use_stm.block.stms.index(use_stm)
        use_attrs = [ir for ir in use_stm.kids() if ir.is_a(ATTR)]
        qsym = phi.var.qualified_symbol()

        def replace_attr(attr, qsym, newattr):
            if attr.is_a(ATTR):
                if attr.exp.qualified_symbol() == qsym:
                    attr.exp = newattr
                    return
                return replace_attr(attr.exp, qsym, newattr)
        for use_attr in use_attrs:
            if use_attr.attr.typ.is_object():
                continue
            if use_attr.exp.qualified_symbol() == qsym:
                uphi = UPHI(use_attr.clone())
                uphi.lineno = use_stm.lineno
                uphi.ps = phi.ps[:]
                for arg in phi.args:
                    uarg = use_attr.clone()
                    uarg.lineno = use_stm.lineno
                    replace_attr(uarg, qsym, arg.clone())
                    uphi.args.append(uarg)
                use_stm.block.insert_stm(insert_idx, uphi)

    def _need_rename(self, sym, qsym):
        if not sym.typ.is_object():
            return False
        if sym.name == env.self_name:
            return False
        if sym.scope.is_module() or sym.scope.is_namespace():
            return False
        if sym.is_param():
            return False
        if sym in [copy for _, copy, _ in self.scope.params]:
            return False
        idx = qsym.index(sym)
        if idx > 0:
            if not self._need_rename(qsym[idx - 1], qsym):
                return False
        return True
