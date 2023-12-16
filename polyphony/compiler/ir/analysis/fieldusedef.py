from collections import defaultdict
from ..irvisitor import IRVisitor
from ..ir import *
from ..irhelper import qualified_symbols
from ..scope import Scope
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

    def add_var_def(self, scope: Scope, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        qsym = qualified_symbols(var, scope)
        key = self.qsym2key(qsym)
        self._def_qsym2stm[key].add(stm)

    def remove_var_def(self, scope: Scope, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        qsym = qualified_symbols(var, scope)
        key = self.qsym2key(qsym)
        self._def_qsym2stm[key].discard(stm)

    def add_var_use(self, scope: Scope, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        qsym = qualified_symbols(var, scope)
        key = self.qsym2key(qsym)
        self._use_qsym2stm[key].add(stm)

    def remove_var_use(self, scope: Scope, var, stm):
        assert var.is_a(ATTR) and stm.is_a(IRStm)
        qsym = qualified_symbols(var, scope)
        key = self.qsym2key(qsym)
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
        self.visit(ir.func)
        self._visit_args(ir)

    def visit_NEW(self, ir):
        self.visit(ir.func)
        self._visit_args(ir)

    def visit_ATTR(self, ir):
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self.table.add_var_use(self.scope, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self.table.add_var_def(self.scope, ir, self.current_stm)
        else:
            assert False


class FieldUseDef(object):
    def process(self, module):
        assert module.is_module()
        self.module = module
        self.scopes = self._collect_scopes(module)
        self.usedef_tables = {}
        for scope in self.scopes:
            table = FieldUseDefDetector().process(scope)
            self.usedef_tables[scope] = table
        self.module.field_usedef = self

    def _collect_scopes(self, scope):
        scopes = set()
        workers = set([w for w in scope.workers])
        scopes |= workers
        for w in workers:
            scopes |= self._collect_scopes(w)
        subscopes = (set(scope.children) | scope.closures)
        for sub in subscopes:
            if sub.is_worker():  # exclude uninstantiated worker
                continue
            if sub.is_lib():
                continue
            scopes.add(sub)
            scopes |= self._collect_scopes(sub)
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
