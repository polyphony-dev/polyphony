import sys
from collections import OrderedDict, defaultdict, deque
from .dominator import DominatorTreeBuilder, DominanceFrontierBuilder
from .symbol import Symbol
from .ir import Ctx, TEMP, PHI, JUMP, MSTORE
from .type import Type
from .usedef import UseDefDetector
from .varreplacer import VarReplacer
from logging import getLogger
logger = getLogger(__name__)
import pdb

class SSAFormTransformer:
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

    def _is_always_single_assigned(self, sym):
        return sym.is_condition() or sym.is_temp() or sym.is_param() or sym.is_function() or sym.is_return() or Type.is_object(sym.typ)


    def _insert_phi(self):
        phis = defaultdict(list)

        for sym, def_blocks in self.usedef._sym_defs_blk.items():
            # skip a single assigned symbol
            if self._is_always_single_assigned(sym):
                continue
            #logger.debug('{} define blocks'.format(sym.name))
            #logger.debug(', '.join([b.name for b in def_blocks]))
            while def_blocks:
                def_block = def_blocks.pop()
                logger.debug(def_block.name)
                if def_block not in self.dominance_frontier:
                    continue
                for df in self.dominance_frontier[def_block]:
                    logger.log(0, 'DF of ' + def_block.name + ' = ' + df.name)
                    if sym not in phis[df]:
                        #logger.debug('phis[{}] append {}'.format(df.name, sym.name))
                        phis[df].append(sym)
                        #insert phi to df
                        var = TEMP(sym, Ctx.STORE)
                        phi = PHI(var)
                        phi.block = df
                        df.stms.insert(0, phi)
			#The phi has the definintion of the variable
			#so we must add the phi to the df_blocks if needed
                        if sym not in self.usedef.get_def_syms_by_blk(df):
                            def_blocks.add(df)
                        #this must call after the above checking
                        self.usedef.add_var_def(var, phi)
                        self.phis.append(phi)


    def _rename(self):
        count = {}
        stack = {}
        using_syms = set()
        for blk in self.scope.blocks:
            for sym in self.usedef.get_def_syms_by_blk(blk):
                using_syms.add(sym)
            for sym in self.usedef.get_use_syms_by_blk(blk):
                using_syms.add(sym)
        for sym in using_syms:
            count[sym] = 0
            stack[sym] = [0]

        new_syms = set()
        self._rename_rec(self.scope.blocks[0], count, stack, new_syms)

        for var, sym in new_syms:
            assert var.is_a(TEMP)
            if self._is_always_single_assigned(sym):
                continue
            var.sym = sym


    def _get_phis(self, block):
        return filter(lambda stm: stm.is_a(PHI), block.stms)

    def _need_rename(self, defvar, stm):
        if not Type.is_list(defvar.sym.typ):
            return True
        elif stm.is_a(MOVE):
            if stm.dst is defvar:
                return True
        elif stm.is_a(PHI):
                return True
        return False

    def _rename_rec(self, block, count, stack, new_syms):
        for stm in block.stms:
            if not stm.is_a(PHI):
                for use in self.usedef.get_use_vars_by_stm(stm):
                    assert use.is_a(TEMP)
                    i = stack[use.sym][-1]
                    new_name = use.sym.name + '#' + str(i)
                    new_sym = self.scope.inherit_sym(use.sym, new_name)
                    logger.debug(str(new_sym) + ' ancestor is ' + str(use.sym))
                    new_syms.add((use, new_sym))
            #this loop includes PHI
            for d in self.usedef.get_def_vars_by_stm(stm):
                assert d.is_a(TEMP)
                if self._need_rename(d, stm):
                    logger.debug('count up ' + str(stm))
                    count[d.sym] += 1
                i = count[d.sym]
                stack[d.sym].append(i)
                new_name = d.sym.name + '#' + str(i)
                new_sym = self.scope.inherit_sym(d.sym, new_name)
                logger.debug(str(new_sym) + ' ancestor is ' + str(d.sym))
                new_syms.add((d, new_sym))
        #into successors
        for succ in block.succs:
            #collect phi
            phis = self._get_phis(succ)
            for phi in phis:
                i = stack[phi.var.sym][-1]
                if i > 0:
                    new_name = phi.var.sym.name + '#' + str(i)
                    new_sym = self.scope.inherit_sym(phi.var.sym, new_name)
                    #logger.debug(str(new_sym) + ' ancestor is ' + str(phi.var.sym))
                    var = TEMP(new_sym, Ctx.LOAD)
                    var.block = succ
                    phi.args.append((var, block))
                    
        for c in self.tree.get_children_of(block):
            self._rename_rec(c, count, stack, new_syms)
        for stm in block.stms:
            for d in self.usedef.get_def_vars_by_stm(stm):
                stack[d.sym].pop()



    def dump_df(self):
        for node, dfs in sorted(self.dominance_frontier.items(), key=lambda n: n[0].name):
            logger.debug('DF of ' + node.name + ' is ...' + ', '.join([df.name for df in dfs]))


    def _compute_dominance_frontier(self):
        dtree_builder = DominatorTreeBuilder(self.scope)
        tree = dtree_builder.process()
        tree.dump()
        self.tree = tree

        first_block = self.scope.blocks[0]
        df_builder = DominanceFrontierBuilder()
        self.dominance_frontier = df_builder.process(first_block, tree)

    def _remove_useless_phi(self):
        udd = UseDefDetector()
        udd.process(self.scope)
        usedef = self.scope.usedef

        def get_sym_if_having_only_1(phi):
            syms = [arg.sym for arg, blk in phi.args if arg.sym is not phi.var.sym]
            if syms and all(syms[0] is s for s in syms):
                return syms[0]
            else:
                return None
        worklist = deque()
        for blk in self.scope.blocks:
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
        for blk in self.scope.blocks:
            for phi in self._get_phis(blk):
                removes = []
                for arg, blk in phi.args:
                    if arg.is_a(TEMP) and arg.sym is phi.var.sym:
                        removes.append((arg, blk))
                for rm in removes:
                    phi.args.remove(rm)


from .scope import Scope
from .block import Block
from .ir import BINOP, RELOP, CONST, MOVE, CJUMP
from .usedef import UseDefDetector

def main():
    scope = Scope.create(None, 's')
    b1 = Block.create(scope)
    b2 = Block.create(scope)
    b1.connect(b2)
    b3 = Block.create(scope)
    b4 = Block.create(scope)
    b2.connect_branch(b3, True)
    b2.connect_branch(b4, False)
    b5 = Block.create(scope)
    b6 = Block.create(scope)
    b3.connect_branch(b5, True)
    b3.connect_branch(b6, False)
    b7 = Block.create(scope)
    b5.connect(b7)
    b6.connect(b7)
    b7.connect_loop(b2)
    b7.merge_branch(b3)

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
