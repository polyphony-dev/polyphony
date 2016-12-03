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
        self._cleanup_phi()

    def _insert_phi(self):
        phi_symbols = defaultdict(list)

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
                    phi = PHI(var)
                    phi.block = df
                    df.stms.insert(0, phi)
                    #The phi has the definintion of the variable
                    #so we must add the phi to the df_blocks if needed
                    if qsym not in self.usedef.get_def_qsyms_by_blk(df):
                        def_blocks.add(df)
                    #this must call after the above checking
                    self._add_phi_var_to_usedef(var, phi)
                    
                    self.phis.append(phi)

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
            qstack[key] = [0]

        self.new_syms = set()
        self._rename_rec(self.scope.root_block, qcount, qstack)

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
                    i = stack[key][-1]
                    self._add_new_sym(use, i)
            #this loop includes PHI
            for d in self.usedef.get_def_vars_by_stm(stm):
                assert d.is_a([TEMP, ATTR])
                key = d.qualified_symbol()
                if self._need_rename(d.symbol()):
                    logger.debug('count up ' + str(d) + ' ' + str(stm))
                    count[key] += 1
                i = count[key]
                stack[key].append(i)
                self._add_new_sym(d, i)
                if stm.is_a(PHI) and d.is_a(ATTR):
                    self._add_new_sym_rest(d.exp, stack)
        #into successors
        for succ in block.succs:
            #collect phi
            phis = self._get_phis(succ)
            for phi in phis:
                self._add_new_phi_arg(phi, phi.var, stack, block)
                continue
                    
        for c in self.tree.get_children_of(block):
            self._rename_rec(c, count, stack)
        for stm in block.stms:
            for d in self.usedef.get_def_vars_by_stm(stm):
                key = d.qualified_symbol()
                if key in stack and stack[key]:
                    stack[key].pop()

    def _add_new_phi_arg(self, phi, var, stack, block, is_tail_attr = True):
        key = var.qualified_symbol()
        i = stack[key][-1]
        if is_tail_attr:
            if i > 0:
                var = var.clone()
                var.ctx = Ctx.LOAD
                phi.args.append((var, block))
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
        i = stack[key][-1]
        self.new_syms.add((var, i))
        if var.is_a(ATTR):
            self._add_new_sym_rest(var.exp, stack)

    def _qsym_to_var(self, qsym, ctx):
        if len(qsym) == 1:
            return TEMP(qsym[0], ctx)
        else:
            exp = self._qsym_to_var(qsym[:-1], Ctx.LOAD)
            return ATTR(exp, qsym[-1], ctx)

    def _get_phis(self, block):
        return filter(lambda stm: stm.is_a(PHI), block.stms)

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

        first_block = self.scope.root_block
        df_builder = DominanceFrontierBuilder()
        self.dominance_frontier = df_builder.process(first_block, tree)

    def _remove_useless_phi(self):
        udd = UseDefDetector()
        udd.process(self.scope)
        usedef = self.scope.usedef

        def get_sym_if_having_only_1(phi):
            syms = [arg.symbol() for arg, blk in phi.args if arg.symbol() is not phi.var.symbol()]
            if syms and all(syms[0] is s for s in syms):
                return syms[0]
            else:
                return None
        worklist = deque()
        for blk in self.scope.traverse_blocks():
            worklist.extend(self._get_phis(blk))
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
            for phi in self._get_phis(blk):
                removes = []
                for arg, blk in phi.args:
                    if arg.is_a(TEMP) and arg.symbol() is phi.var.symbol():
                        removes.append((arg, blk))
                for rm in removes:
                    phi.args.remove(rm)

class ScalarSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def _need_rename(self, sym):
        return not (sym.is_condition() or sym.is_temp() or sym.is_param() or sym.is_function() or sym.is_return() or Type.is_object(sym.typ))

class ObjectSSATransformer(SSATransformerBase):
    def __init__(self):
        super().__init__()

    def _need_rename(self, sym):
        return Type.is_object(sym.typ)



                    
from .scope import Scope
from .block import Block
from .ir import BINOP, RELOP, CONST, MOVE, CJUMP
from .usedef import UseDefDetector

def main():
    scope = Scope.create(None, 's')
    b1 = Block(scope)
    b2 = Block(scope)
    b1.connect(b2)
    b3 = Block(scope)
    b4 = Block(scope)
    b2.connect(b3)
    b2.connect(b4)
    b5 = Block(scope)
    b6 = Block(scope)
    b3.connect(b5)
    b3.connect(b6)
    b7 = Block(scope)
    b5.connect(b7)
    b6.connect(b7)
    b7.connect_loop(b2)
    
    i = Symbol.new('i', scope)
    j = Symbol.new('j', scope)
    k = Symbol.new('k', scope)
    ret = Symbol.new(Symbol.return_prefix, scope)
    b1.append_stm(MOVE(TEMP(i,Ctx.STORE), CONST(1)))
    b1.append_stm(MOVE(TEMP(j,Ctx.STORE), CONST(1)))
    b1.append_stm(MOVE(TEMP(k,Ctx.STORE), CONST(0)))
    b2.append_stm(CJUMP(RELOP('Lt', TEMP(k, Ctx.LOAD), CONST(100)), b3, b4))
    b3.append_stm(CJUMP(RELOP('Lt', TEMP(j, Ctx.LOAD), CONST(20)), b5, b6))
    b4.append_stm(MOVE(TEMP(ret,Ctx.STORE), TEMP(j, Ctx.LOAD)))
    b5.append_stm(MOVE(TEMP(j,Ctx.STORE), TEMP(i,Ctx.LOAD)))
    b5.append_stm(MOVE(TEMP(k,Ctx.STORE), BINOP('Add', TEMP(k,Ctx.LOAD), CONST(1))))
    b6.append_stm(MOVE(TEMP(j,Ctx.STORE), TEMP(k,Ctx.LOAD)))
    b6.append_stm(MOVE(TEMP(k,Ctx.STORE), BINOP('Add', TEMP(k,Ctx.LOAD), CONST(2))))

    Scope.dump()

    usedef = UseDefDetector()
    usedef.process_scope(scope)
     
    ssa = SSAFormTransformer()
    ssa.process(scope)

    Scope.dump()


if __name__ == '__main__':
    main()
