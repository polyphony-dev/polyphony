import sys
from collections import OrderedDict, defaultdict, deque
from .dominator import DominatorTreeBuilder, DominanceFrontierBuilder
from .symbol import Symbol
from .ir import *
from .type import Type
from .usedef import UseDefDetector
from .varreplacer import VarReplacer
from logging import getLogger
logger = getLogger(__name__)
import pdb

class SSATransformerBase:
    def __init__(self):
        pass

    def process(self, scope):
        if scope.is_class():
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
        self._cleanup_phi()

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
        for qsym, def_blocks in self.usedef._qsym_defs_blk.items():
            assert isinstance(qsym, tuple)
            if not self._need_rename(qsym[-1]):
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
                        assert Type.is_object(qsym[0].typ)
                        var.class_scope = Type.extra(qsym[0].typ)
                    phi = self._new_phi(var, df)
                    df.insert_stm(0, phi)
                    #The phi has the definintion of the variable
                    #so we must add the phi to the df_blocks if needed
                    if qsym not in self.usedef.get_def_qsyms_by_blk(df):
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
        phi.args = [CONST(0)] * len(df.preds)
        phi.defblks = [None] * len(df.preds)
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
            for var in self.usedef.get_def_vars_by_blk(blk):
                using_vars.add(var)
            for var in self.usedef.get_use_vars_by_blk(blk):
                using_vars.add(var)
        for var in using_vars:
            key = var.qualified_symbol()
            qcount[key] = 0
            qstack[key] = [(0, None)]

        self.new_syms = set()
        self._rename_rec(self.scope.entry_block, qcount, qstack)

        for var, version in self.new_syms:
            assert var.is_a([TEMP, ATTR])
            if self._need_rename(var.symbol()):
                new_name = var.symbol().name + '#' + str(version)
                new_sym = self.scope.inherit_sym(var.symbol(), new_name)
                logger.debug(str(new_sym) + ' ancestor is ' + str(var.symbol()))
                var.set_symbol(new_sym)

    def _rename_rec(self, block, count, stack):
        for stm in block.stms:
            if not stm.is_a(PHI):
                for use in self.usedef.get_use_vars_by_stm(stm):
                    assert use.is_a([TEMP, ATTR])
                    key = use.qualified_symbol()
                    i, _ = stack[key][-1]
                    self._add_new_sym(use, i)
            #this loop includes PHI
            for d in self.usedef.get_def_vars_by_stm(stm):
                #print(stm, d)
                assert d.lineno > 0
                assert d.is_a([TEMP, ATTR])
                key = d.qualified_symbol()
                if self._need_rename(d.symbol()):
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
            for d in self.usedef.get_def_vars_by_stm(stm):
                key = d.qualified_symbol()
                if key in stack and stack[key]:
                    stack[key].pop()

    def _add_new_phi_arg(self, phi, var, stack, block, is_tail_attr = True):
        key = var.qualified_symbol()
        i, v = stack[key][-1]
        if is_tail_attr:
            if i > 0:
                var = var.clone()
                var.ctx = Ctx.LOAD
                var.lineno = v.lineno
                idx = phi.block.preds.index(block)
                phi.args[idx] = var
                phi.defblks[idx] = block
                self._add_new_sym(var, i)
        else:
            self._add_new_sym(var, i)
        
        if var.is_a(ATTR):
            self._add_new_phi_arg(phi, var.exp, stack, block, is_tail_attr=False)


    def _need_rename(self, sym):
        return False

    def _add_new_sym(self, var, version):
        assert var.is_a([TEMP, ATTR])
        if self._need_rename(var.symbol()):
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

    def _need_name_version(self, defvar, stm):
        if not Type.is_list(defvar.symbol().typ):
            return True
        elif stm.is_a(MOVE):
            if stm.dst is defvar:
                return True
        elif stm.is_a(PHI):
            return True
        return False

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
            syms = [arg.symbol() for arg in phi.args if arg.is_a([TEMP, ATTR]) and arg.symbol() is not phi.var.symbol()]
            if syms and all(syms[0] is s for s in syms):
                return syms[0]
            else:
                return None
        worklist = deque()
        for blk in self.scope.traverse_blocks():
            worklist.extend(blk.collect_stms(PHI))
        while worklist:
            phi = worklist.popleft()
            if not phi.args:
                #assert False
                logger.debug('remove ' + str(phi))
                phi.block.stms.remove(phi)
                #pass
            else:
                sym = get_sym_if_having_only_1(phi)
                if sym:
                    logger.debug('remove ' + str(phi))
                    if phi in phi.block.stms:
                        phi.block.stms.remove(phi)
                    replaces = VarReplacer.replace_uses(phi.var, TEMP(sym, Ctx.LOAD), usedef)
                    for rep in replaces:
                        if rep.is_a(PHI):
                            worklist.append(rep)

    def _cleanup_phi(self):
        for blk in self.scope.traverse_blocks():
            for phi in blk.collect_stms(PHI):
                remove_args = [arg for arg in phi.args if arg.is_a(TEMP) and arg.symbol() is phi.var.symbol()]
                for arg in remove_args:
                    phi.remove_arg(arg)

    def _concat_predicates(self, predicates, op):
        if not predicates:
            return None
        concat = predicates[0]
        for p in predicates[1:]:
            concat = BINOP(op, concat, p)
        return concat

    def _idom_path(self, blk, path):
        path.append(blk)
        idom = self.tree.get_parent_of(blk)
        if not idom:
            return
        self._idom_path(idom, path)

    def _insert_predicate(self):
        usedef = self.scope.usedef

        for blk in self.scope.traverse_blocks():
            phis = blk.collect_stms(PHI)
            if not phis:
                continue
            phi_predicates = [pred.path_exp if pred.path_exp else CONST(1) for pred in blk.preds]
            for phi in phis:
                phi.ps = phi_predicates[:]
                assert len(phi.ps) == len(phi.args)

class ScalarSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def _need_rename(self, sym):
        return not (sym.is_condition() or sym.is_param() or sym.is_return() or Type.is_class(sym.typ) or Type.is_object(sym.typ) or Type.is_tuple(sym.typ))

from .tuple import TupleTransformer
class TupleSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        if scope.is_class():
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
                uses = usedef.get_use_stms_by_qsym(phi.var.qualified_symbol())
                for use in uses:
                    self._insert_use_phi(phi, use)

    def _insert_use_phi(self, phi, use_stm):
        insert_idx = use_stm.block.stms.index(use_stm)
        use_mrefs = [ir for ir in use_stm.find_irs(MREF) if Type.is_tuple(ir.mem.symbol().typ)]
        qsym = phi.var.qualified_symbol()
        def replace_attr(mref, qsym, newmem):
            if mref.mem.qualified_symbol() == qsym:
                mref.mem = newmem
                
        for mref in use_mrefs:
            if mref.mem.qualified_symbol() == qsym:
                tmp = self.scope.add_temp('{}_{}'.format(Symbol.temp_prefix, mref.mem.symbol().orig_name()))
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

    def _need_rename(self, sym):
        return Type.is_tuple(sym.typ) and not sym.is_param()

class ObjectSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        if scope.is_class():
            return
        super().process(scope)
        self._process_use_phi()

    def _process_use_phi(self):
        usedef = self.scope.usedef
        for blk in self.scope.traverse_blocks():
            phis = blk.collect_stms(PHI)
            for phi in phis:
                uses = usedef.get_use_stms_by_qsym(phi.var.qualified_symbol())
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
            if Type.is_object(use_attr.attr.typ):
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
                    
    def _need_rename(self, sym):
        return Type.is_object(sym.typ)

