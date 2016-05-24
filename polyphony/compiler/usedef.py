from collections import defaultdict
from .irvisitor import IRVisitor
from .ir import Ctx, TEMP, CONST, IRStm
from .type import Type
from .env import env
from logging import getLogger
logger = getLogger(__name__)

class UseDefTable:
    def __init__(self):
        self._sym_defs_stm = defaultdict(set)
        self._sym_uses_stm = defaultdict(set)
        self._var_defs_stm = defaultdict(set)
        self._var_uses_stm = defaultdict(set)
        self._sym_defs_blk = defaultdict(set)
        self._sym_uses_blk = defaultdict(set)
        self._stm_defs_var = defaultdict(set)
        self._stm_uses_var = defaultdict(set)
        self._blk_defs_var = defaultdict(set)
        self._blk_uses_var = defaultdict(set)
        self._stm_uses_const = defaultdict(set)

    def add_var_def(self, var, stm):
        assert var.is_a(TEMP) and stm.is_a(IRStm)
        self._sym_defs_stm[var.sym].add(stm)
        self._var_defs_stm[var].add(stm)
        self._sym_defs_blk[var.sym].add(stm.block)
        self._stm_defs_var[stm].add(var)
        self._blk_defs_var[stm.block].add(var)

    def remove_var_def(self, var, stm):
        assert var.is_a(TEMP) and stm.is_a(IRStm)
        self._sym_defs_stm[var.sym].discard(stm)
        self._var_defs_stm[var].discard(stm)
        self._sym_defs_blk[var.sym].discard(stm.block)
        self._stm_defs_var[stm].discard(var)
        self._blk_defs_var[stm.block].discard(var)

    def add_var_use(self, var, stm):
        assert var.is_a(TEMP) and stm.is_a(IRStm)
        self._sym_uses_stm[var.sym].add(stm)
        self._var_uses_stm[var].add(stm)
        self._sym_uses_blk[var.sym].add(stm.block)
        self._stm_uses_var[stm].add(var)
        self._blk_uses_var[stm.block].add(var)

    def remove_var_use(self, var, stm):
        assert var.is_a(TEMP) and stm.is_a(IRStm)
        self._sym_uses_stm[var.sym].discard(stm)
        self._var_uses_stm[var].discard(stm)
        self._sym_uses_blk[var.sym].discard(stm.block)
        self._stm_uses_var[stm].discard(var)
        self._blk_uses_var[stm.block].discard(var)

    def add_const_use(self, c, stm):
        assert c.is_a(CONST) and stm.is_a(IRStm)
        self._stm_uses_const[stm].add(c)

    def remove_const_use(self, c, stm):
        assert c.is_a(CONST) and stm.is_a(IRStm)
        self._stm_uses_const[stm].discard(c)

    def add_use(self, v, stm):
        if v.is_a(TEMP):
            self.add_var_use(v, stm)
        elif v.is_a(CONST):
            self.add_const_use(v, stm)
        else:
            assert False

    def remove_use(self, v, stm):
        if v.is_a(TEMP):
            self.remove_var_use(v, stm)
        elif v.is_a(CONST):
            self.remove_const_use(v, stm)
        else:
            assert False

    def remove_uses(self, vs, stm):
        for v in vs:
            self.remove_use(v, stm)

    def get_def_stms_by_sym(self, sym):
        return self._sym_defs_stm[sym]

    def get_use_stms_by_sym(self, sym):
        return self._sym_uses_stm[sym]

    def get_def_stms_by_var(self, var):
        return self._var_defs_stm[var]

    def get_use_stms_by_var(self, var):
        return self._var_uses_stm[var]

    def get_def_blks_by_sym(self, sym):
        return self._sym_defs_blk[sym]

    def get_use_blks_by_sym(self, sym):
        return self._sym_uses_blk[sym]

    def get_def_vars_by_stm(self, stm):
        return self._stm_defs_var[stm]

    def get_use_vars_by_stm(self, stm):
        return self._stm_uses_var[stm]

    def get_use_consts_by_stm(self, stm):
        return self._stm_uses_const[stm]

    def get_def_syms_by_blk(self, blk):
        return set([v.sym for v in self._blk_defs_var[blk]])

    def get_use_syms_by_blk(self, blk):
        return set([v.sym for v in self._blk_uses_var[blk]])

    def get_def_vars_by_blk(self, blk):
        return self._blk_defs_var[blk]

    def get_use_vars_by_blk(self, blk):
        return self._blk_uses_var[blk]

    def get_all_syms(self):
        return self._sym_defs_stm.keys()

    def get_all_vars(self):
        vs = list(self._var_defs_stm.keys())
        vs.extend(self._var_uses_stm.keys())
        return vs

    def dump(self):
        logger.debug('statements that has symbol defs')
        for sym, stms in self._sym_defs_stm.items():
            logger.debug(sym)
            for stm in stms:
                logger.debug('    ' + str(stm))

        logger.debug('blocks that has symbol defs')
        for sym, blks in self._sym_defs_blk.items():
            logger.debug(sym)
            for blk in blks:
                logger.debug('    ' + blk.name)

        logger.debug('statements that has symbol uses')
        for sym, stms in self._sym_uses_stm.items():
            logger.debug(sym)
            for stm in stms:
                logger.debug('    ' + str(stm))

        logger.debug('blocks that has symbol uses')
        for sym, blks in self._sym_uses_blk.items():
            logger.debug(sym)
            for blk in blks:
                logger.debug('    ' + blk.name)


class UseDefDetector(IRVisitor):
    def __init__(self):
        super().__init__()
        self.table = UseDefTable()

    def _process_scope_done(self, scope):
        scope.usedef = self.table

    def visit_UNOP(self, ir):
        self.visit(ir.exp)

    def visit_BINOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_RELOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def _visit_args(self, ir):
        for arg in ir.args:
            self.visit(arg)
            if env.compile_phase >= env.PHASE_4 and arg.is_a(TEMP) and Type.is_list(arg.sym.typ):
                memnode = None
                if env.memref_graph:
                    memnode = env.memref_graph.node(arg.sym)
                if memnode and not memnode.is_writable():
                    continue
                self.table.add_var_def(arg, self.current_stm)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        self._visit_args(ir)

    def visit_SYSCALL(self, ir):
        self._visit_args(ir)

    def visit_CTOR(self, ir):
        self._visit_args(ir)

    def visit_CONST(self, ir):
        self.table.add_const_use(ir, self.current_stm)

    def visit_MREF(self, ir):
        self.visit(ir.mem)
        self.visit(ir.offset)

    def visit_MSTORE(self, ir):
        self.visit(ir.mem)
        self.visit(ir.offset)
        self.visit(ir.exp)

    def visit_ARRAY(self, ir):
        for item in ir.items:
            self.visit(item)

    def visit_TEMP(self, ir):
        if ir.ctx & Ctx.LOAD:
            self.table.add_var_use(ir, self.current_stm)
        if ir.ctx & Ctx.STORE:
            self.table.add_var_def(ir, self.current_stm)

    def visit_ATTR(self, ir):
        self.visit(ir.exp)

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)
        if ir.uses:
            for use in ir.uses:
                self.visit(use)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)
        if ir.uses:
            for use in ir.uses:
                self.visit(use)

    def visit_JUMP(self, ir):
        if ir.uses:
            for use in ir.uses:
                self.visit(use)
        #pass

    def visit_RET(self, ir):
        self.visit(ir.exp)

    def visit_MOVE(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)

    def visit_PHI(self, ir):
        self.visit(ir.var)
        for arg, blk in ir.args:
            self.visit(arg)

