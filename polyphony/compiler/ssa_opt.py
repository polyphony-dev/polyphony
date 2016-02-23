from collections import deque
from .ir import CONST, BINOP, RELOP, TEMP, MREF, MSTORE, CALL, MOVE, CJUMP, JUMP, PHI
from .varreplacer import VarReplacer
from .constantfolding import ConstantFolding
from .usedef import UseDefDetector
from logging import getLogger
logger = getLogger(__name__)

class SSAOptimizer:
    def process(self, scope):
        usedef = scope.usedef
        worklist = deque()
        for block in scope.blocks:
            worklist.extend(block.stms)

        while worklist:
            stm = worklist.popleft()
            if stm not in stm.block.stms:
                continue
            logger.debug('...' + str(stm))
            if isinstance(stm, PHI):
                self._optimize_phi(stm, worklist, usedef)
                continue

            if isinstance(stm, MOVE):
                if self._optimize_move(stm, worklist, usedef):
                    continue

            const_fold = ConstantFolding()
            new_stm = const_fold.process_stm(scope, stm)
            assert new_stm
            if const_fold.modified_stms:
                worklist.extend(const_fold.modified_stms)
            if new_stm is not stm:
                stm.block.replace_stm(stm, new_stm)

        self.eliminate_moves(scope)

    def eliminate_moves(self, scope):
        udd = UseDefDetector()
        udd.process(scope)
        usedef = scope.usedef


        allsyms = list(usedef.get_all_syms())
        for sym in allsyms:
            if sym.is_return() or sym.is_condition():
                continue
            defstms = usedef.get_sym_defs_stm(sym)
            usestms = usedef.get_sym_uses_stm(sym)
            #remove unused stm
            if len(defstms) == 1 and len(usestms) == 0:
                defstm = list(defstms)[0]
                if isinstance(defstm, MOVE):
                    defvar = defstm.dst
                elif isinstance(defstm, PHI):
                    defvar = defstm.var
                else:
                    assert False
                defstm.block.stms.remove(defstm)
                usedef.remove_var_def(defvar, defstm)
                uses = list(usedef.get_stm_uses_var(defstm))
                for u in uses:
                    usedef.remove_var_use(u, defstm)

            #eliminate var that used only once
            elif len(defstms) == 1 and len(usestms) == 1:
                defstm = list(defstms)[0]
                usestm = list(usestms)[0]
                if isinstance(defstm, MOVE) and isinstance(usestm, MOVE) and isinstance(usestm.src, TEMP):
                    # 'a' def : a = exp
                    # 'a' use : y = a
                    # result  : y = exp
                    usestm.block.stms.remove(usestm)
                    usedef.remove_var_use(usestm.src, usestm)
                    usedef.remove_var_def(usestm.dst, usestm)
                    usedef.remove_var_def(defstm.dst, defstm)
                    defstm.dst = usestm.dst
                    usedef.add_var_def(defstm.dst, defstm)

    def _optimize_phi(self, phi, worklist, usedef):
        # All same sources can be replace by the one of them
        # before : a = phi(b, b, ..., b)
        # after  : a = b
        return
        if self._is_same_sources(phi.args):
            src = phi.args[0][0]
            new_stm = MOVE(phi.var, src)
            self._replace_stm(phi, new_stm)
            usedef.remove_uses(phi.argv(), phi)
            usedef.remove_var_def(phi.var, phi)
            usedef.add_use(new_stm.src, new_stm)
            usedef.add_var_def(new_stm.dst, new_stm)
            worklist.append(new_stm)
        #FIXME: To generalize (In case of more than 2 args)
        elif len(phi.argv()) == 2:
            if isinstance(phi.args[0][0], TEMP) and phi.var.sym is phi.args[0][0].sym:
                phi.block.stms.remove(phi)
                replaces = VarReplacer.replace_uses(phi.var, phi.args[1][0], usedef)
                worklist.extend(replaces)
                usedef.remove_var_def(phi.var, phi)
                usedef.remove_use(phi.argv()[1], phi)

            elif isinstance(phi.args[1][0], TEMP) and phi.var.sym is phi.args[1][0].sym:
                phi.block.stms.remove(phi)
                replaces = VarReplacer.replace_uses(phi.var, phi.args[0][0], usedef)
                worklist.extend(replaces)
                usedef.remove_var_def(phi.var, phi)
                usedef.remove_use(phi.argv()[0], phi)


    def _optimize_move(self, mv, worklist, usedef):
        #if isinstance(mv.src, TEMP) and mv.src.sym.is_memory():
        #    return False
        #if mv.dst.sym.is_memory():
        #    return False
        if isinstance(mv.src, TEMP) and mv.src.sym.is_param():
            return False
        if mv.dst.sym.is_return():
            return False
        #FIXME: Propagation must track the control path
        #constant propargation or copypropagation for move

        #To avoid SSA simple ordering problem
        if (isinstance(mv.src, TEMP) and not self._is_phi_target(mv.src, usedef) and not self._is_phi_src(mv.dst, usedef)) or isinstance(mv.src, CONST):
            mv.block.stms.remove(mv)
            replaces = VarReplacer.replace_uses(mv.dst, mv.src, usedef)
            worklist.extend(replaces)
            usedef.remove_var_def(mv.dst, mv)
            usedef.remove_use(mv.src, mv)
            return True
        return False

    def _is_phi_target(self, var, usedef):
        assert isinstance(var, TEMP)
        defstms = usedef.get_sym_defs_stm(var.sym)
        for defstm in defstms:
            if isinstance(defstm, PHI):
                return True
        return False                        


    def _is_phi_src(self, var, usedef):
        assert isinstance(var, TEMP)
        usestms = usedef.get_sym_uses_stm(var.sym)
        for usestm in usestms:
            if isinstance(usestm, PHI):
                return True
        return False                        


    def _replace_stm(self, old, new):
        block = old.block
        assert old in block.stms
        idx = block.stms.index(old)
        block.stms[idx] = new
        new.block = block
        new.lineno = old.lineno

    def _is_same_sources(self, exprs):
        if not exprs:
            return False
        src, blk = exprs[0]
        
        if isinstance(src, CONST):
            for other, _ in exprs[1:]:
                if not isinstance(other, CONST):
                    return False
                if src.value != other.value:
                    return False
            return True
        elif isinstance(src, TEMP):
            for other, _ in exprs[1:]:
                if not isinstance(other, TEMP):
                    return False
                if src.sym is not other.sym:
                    return False
            return True
        return False


