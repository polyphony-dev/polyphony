from collections import defaultdict
from .irvisitor import IRVisitor
from .ir import *
from .block import Block
from .env import env
from .symbol import Symbol
from logging import getLogger
logger = getLogger(__name__)


class UseDefTable(object):
    def __init__(self):
        self._def_sym2stm = defaultdict(set)
        self._use_sym2stm = defaultdict(set)
        self._def_var2stm = defaultdict(set)
        self._use_var2stm = defaultdict(set)
        self._def_sym2blk = defaultdict(set)
        self._use_sym2blk = defaultdict(set)
        self._def_stm2var = defaultdict(set)
        self._use_stm2var = defaultdict(set)
        self._def_blk2var = defaultdict(set)
        self._use_blk2var = defaultdict(set)
        self._use_stm2const = defaultdict(set)
        self._def_qsym2stm = defaultdict(set)
        self._use_qsym2stm = defaultdict(set)
        self._def_qsym2blk = defaultdict(set)
        self._use_qsym2blk = defaultdict(set)

    def add_var_def(self, var, stm):
        assert var.is_a([TEMP, ATTR]) and stm.is_a(IRStm)
        self._def_sym2stm[var.symbol()].add(stm)
        self._def_qsym2stm[var.qualified_symbol()].add(stm)
        self._def_var2stm[var].add(stm)
        self._def_sym2blk[var.symbol()].add(stm.block)
        self._def_qsym2blk[var.qualified_symbol()].add(stm.block)
        self._def_stm2var[stm].add(var)
        self._def_blk2var[stm.block].add(var)

    def remove_var_def(self, var, stm):
        assert var.is_a([TEMP, ATTR]) and stm.is_a(IRStm)
        self._def_sym2stm[var.symbol()].discard(stm)
        self._def_qsym2stm[var.qualified_symbol()].discard(stm)
        self._def_var2stm[var].discard(stm)
        self._def_sym2blk[var.symbol()].discard(stm.block)
        self._def_qsym2blk[var.qualified_symbol()].discard(stm.block)
        self._def_stm2var[stm].discard(var)
        self._def_blk2var[stm.block].discard(var)

    def add_var_use(self, var, stm):
        assert var.is_a([TEMP, ATTR]) and stm.is_a(IRStm)
        self._use_sym2stm[var.symbol()].add(stm)
        self._use_qsym2stm[var.qualified_symbol()].add(stm)
        self._use_var2stm[var].add(stm)
        self._use_sym2blk[var.symbol()].add(stm.block)
        self._use_qsym2blk[var.qualified_symbol()].add(stm.block)
        self._use_stm2var[stm].add(var)
        self._use_blk2var[stm.block].add(var)

    def remove_var_use(self, var, stm):
        assert var.is_a([TEMP, ATTR]) and stm.is_a(IRStm)
        self._use_sym2stm[var.symbol()].discard(stm)
        self._use_qsym2stm[var.qualified_symbol()].discard(stm)
        self._use_var2stm[var].discard(stm)
        self._use_sym2blk[var.symbol()].discard(stm.block)
        self._use_qsym2blk[var.qualified_symbol()].discard(stm.block)
        self._use_stm2var[stm].discard(var)
        self._use_blk2var[stm.block].discard(var)

    def add_const_use(self, c, stm):
        assert c.is_a(CONST) and stm.is_a(IRStm)
        self._use_stm2const[stm].add(c)

    def remove_const_use(self, c, stm):
        assert c.is_a(CONST) and stm.is_a(IRStm)
        self._use_stm2const[stm].discard(c)

    def add_use(self, v, stm):
        if v.is_a([TEMP, ATTR]):
            self.add_var_use(v, stm)
        elif v.is_a(CONST):
            self.add_const_use(v, stm)
        else:
            assert False

    def remove_use(self, v, stm):
        if v.is_a([TEMP, ATTR]):
            self.remove_var_use(v, stm)
        elif v.is_a(CONST):
            self.remove_const_use(v, stm)
        else:
            assert False

    def remove_uses(self, vs, stm):
        for v in vs:
            self.remove_use(v, stm)

    def get_stms_defining(self, key):
        if isinstance(key, Symbol):
            return self._def_sym2stm[key]
        elif isinstance(key, IR) and key.is_a([TEMP, ATTR]):
            return self._def_var2stm[key]
        elif isinstance(key, tuple):
            return self._def_qsym2stm[key]

    def get_stms_using(self, key):
        if isinstance(key, Symbol):
            return self._use_sym2stm[key]
        elif isinstance(key, IR) and key.is_a([TEMP, ATTR]):
            return self._use_var2stm[key]
        elif isinstance(key, tuple):
            return self._use_qsym2stm[key]

    def get_blks_defining(self, sym):
        return self._def_sym2blk[sym]

    def get_blks_using(self, sym):
        return self._use_sym2blk[sym]

    def get_vars_defined_at(self, key):
        if isinstance(key, IRStm):
            return self._def_stm2var[key]
        elif isinstance(key, Block):
            return self._def_blk2var[key]

    def get_vars_used_at(self, key):
        if isinstance(key, IRStm):
            return self._use_stm2var[key]
        elif isinstance(key, Block):
            return self._use_blk2var[key]

    def get_consts_used_at(self, stm):
        return self._use_stm2const[stm]

    def get_syms_defined_at(self, key):
        if isinstance(key, IRStm):
            return set([v.symbol() for v in self._def_stm2var[key]])
        elif isinstance(key, Block):
            return set([v.symbol() for v in self._def_blk2var[key]])

    def get_syms_used_at(self, key):
        if isinstance(key, IRStm):
            return set([v.symbol() for v in self._use_stm2var[key]])
        elif isinstance(key, Block):
            return set([v.symbol() for v in self._use_blk2var[key]])

    def get_qsyms_defined_at(self, key):
        if isinstance(key, IRStm):
            return set([v.qualified_symbol() for v in self._use_stm2var[key]])
        elif isinstance(key, Block):
            return set([v.qualified_symbol() for v in self._use_blk2var[key]])

    def get_all_def_syms(self):
        return self._def_sym2stm.keys()

    def get_all_use_syms(self):
        return self._use_sym2stm.keys()

    def get_all_vars(self):
        vs = list(self._def_var2stm.keys())
        vs.extend(self._use_var2stm.keys())
        return vs

    def dump(self):
        logger.debug('statements that has symbol defs')
        for sym, stms in self._def_sym2stm.items():
            logger.debug(sym)
            for stm in stms:
                logger.debug('    ' + str(stm))

        logger.debug('blocks that has symbol defs')
        for sym, blks in self._def_sym2blk.items():
            logger.debug(sym)
            for blk in blks:
                logger.debug('    ' + blk.name)

        logger.debug('statements that has symbol uses')
        for sym, stms in self._use_sym2stm.items():
            logger.debug(sym)
            for stm in stms:
                logger.debug('    ' + str(stm))

        logger.debug('blocks that has symbol uses')
        for sym, blks in self._use_sym2blk.items():
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

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        self.visit(ir.left)
        self.visit(ir.right)

    def _visit_args(self, ir):
        for _, arg in ir.args:
            self.visit(arg)
            if (env.compile_phase >= env.PHASE_4
                    and arg.is_a([TEMP, ATTR])
                    and arg.symbol().typ.is_list()):
                memnode = None
                if env.memref_graph:
                    memnode = env.memref_graph.node(arg.symbol())
                if memnode and not memnode.is_writable():
                    continue
                self.table.add_var_def(arg, self.current_stm)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        self._visit_args(ir)

    def visit_SYSCALL(self, ir):
        self._visit_args(ir)

    def visit_NEW(self, ir):
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
        self.visit(ir.repeat)
        for item in ir.items:
            self.visit(item)

    def visit_TEMP(self, ir):
        if ir.ctx & Ctx.LOAD:
            self.table.add_var_use(ir, self.current_stm)
        if ir.ctx & Ctx.STORE:
            self.table.add_var_def(ir, self.current_stm)

    def visit_ATTR(self, ir):
        if ir.ctx & Ctx.LOAD:
            self.table.add_var_use(ir, self.current_stm)
        if ir.ctx & Ctx.STORE:
            self.table.add_var_def(ir, self.current_stm)
        self.visit(ir.exp)

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        self.visit(ir.exp)

    def visit_MOVE(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)

    def visit_PHI(self, ir):
        self.visit(ir.var)
        [self.visit(arg) for arg in ir.args if arg]
        [self.visit(p) for p in ir.ps if p]

    def visit_UPHI(self, ir):
        self.visit(ir.var)
        [self.visit(arg) for arg in ir.args if arg]
        [self.visit(p) for p in ir.ps if p]
