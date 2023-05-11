from collections import defaultdict
from ..irvisitor import IRVisitor
from ..ir import *
from ..block import Block
from ..symbol import Symbol
from ..types.type import Type
from logging import getLogger
logger = getLogger(__name__)


class FieldUseDefTable(object):
    def __init__(self):
        self._def_qsym2stm = defaultdict(set)
        self._use_qsym2stm = defaultdict(set)

    def qsym2key(self, qsym):
        if qsym[0].is_self():
            qsym = qsym[1:]
        return qsym

    def add_var_def(self, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        key = self.qsym2key(var.qualified_symbol)
        self._def_qsym2stm[key].add(stm)

    def remove_var_def(self, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        key = self.qsym2key(var.qualified_symbol)
        self._def_qsym2stm[key].discard(stm)

    def add_var_use(self, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        key = self.qsym2key(var.qualified_symbol)
        self._use_qsym2stm[key].add(stm)

    def remove_var_use(self, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        key = self.qsym2key(var.qualified_symbol)
        self._use_qsym2stm[key].discard(stm)

    def get_def_stms(self, qsym):
        assert isinstance(qsym, tuple)
        key = self.qsym2key(qsym)
        return self._def_qsym2stm[key]

    def get_use_stms(self, qsym):
        assert isinstance(qsym, tuple)
        key = self.qsym2key(qsym)
        return self._use_qsym2stm[key]

    def __str__(self):
        s = '--------------------------------\n'
        s += 'statements that has symbol defs\n'
        for qsym, stms in self._def_qsym2stm.items():
            s += f'{qsym}\n'
            for stm in stms:
                s += f'    {stm}\n'
        s += '--------------------------------\n'
        s += 'statements that has symbol uses\n'
        for qsym, stms in self._use_qsym2stm.items():
            s += f'{qsym}\n'
            for stm in stms:
                s += f'    {stm}\n'
        return s

    def dump(self):
        logger.debug(self)


class FieldUseDefDetector(IRVisitor):
    def __init__(self):
        super().__init__()
        self.table = FieldUseDefTable()

    def process(self, scope):
        super().process(scope)
        return self.table

    def _process_block(self, block):
        for stm in block.stms:
            self.visit(stm)

    def _visit_args(self, ir):
        for _, arg in ir.args:
            self.visit(arg)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        self._visit_args(ir)

    def visit_SYSCALL(self, ir):
        self._visit_args(ir)

    def visit_NEW(self, ir):
        self._visit_args(ir)

    def visit_ATTR(self, ir):
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self.table.add_var_use(ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self.table.add_var_def(ir, self.current_stm)
        else:
            assert False


class FieldUseDef(object):
    def process(self, module, driver):
        assert module.is_module()
        self.module = module
        using_scopes = set(driver.scopes)
        self.scopes = self._collect_scopes(module, using_scopes)
        self.usedef_tables = {}
        for scope in self.scopes:
            table = FieldUseDefDetector().process(scope)
            self.usedef_tables[scope] = table
        self.module.field_usedef = self

    def _collect_scopes(self, scope, using_scopes):
        scopes = set()
        workers = set([w for w, _ in scope.workers]) & using_scopes
        scopes |= workers
        for w in workers:
            scopes |= self._collect_scopes(w, using_scopes)
        subscopes = (set(scope.children) | scope.closures) & using_scopes
        for sub in subscopes:
            if sub.is_worker():  # exclude uninstantiated worker
                continue
            if sub.is_lib():
                continue
            scopes.add(sub)
            scopes |= self._collect_scopes(sub, using_scopes)
        return scopes

    def get_def_stms(self, qsym):
        defstms = set()
        for scope in self.scopes:
            table = self.usedef_tables[scope]
            defstms |= table.get_def_stms(qsym)
        return defstms

    def get_use_stms(self, qsym):
        usestms = set()
        for scope in self.scopes:
            table = self.usedef_tables[scope]
            usestms |= table.get_use_stms(qsym)
        return usestms
