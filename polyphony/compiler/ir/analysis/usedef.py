
from collections import defaultdict
from dataclasses import dataclass
from ..irvisitor import IRVisitor
from ..ir import *
from ..irhelper import qualified_symbols
from ..block import Block
from ..symbol import Symbol
from ..scope import Scope
from ..types.type import Type
from ..types import typehelper
from logging import getLogger
logger = getLogger(__name__)


@dataclass(frozen=True)
class UseDefItem:
    sym: Symbol
    qsym: tuple[Symbol]
    var: IRVariable
    stm: IRStm
    blk: Block


class UseDefTable(object):
    def __init__(self):
        self._def_sym2:dict[Symbol, set[UseDefItem]] = defaultdict(set)
        self._use_sym2:dict[Symbol, set[UseDefItem]] = defaultdict(set)
        self._def_qsym2:dict[tuple[Symbol], set[UseDefItem]] = defaultdict(set)
        self._use_qsym2:dict[tuple[Symbol], set[UseDefItem]] = defaultdict(set)
        self._def_var2:dict[IRVariable, set[UseDefItem]] = defaultdict(set)
        self._use_var2:dict[IRVariable, set[UseDefItem]] = defaultdict(set)
        self._def_stm2:dict[IRStm, set[UseDefItem]] = defaultdict(set)
        self._use_stm2:dict[IRStm, set[UseDefItem]] = defaultdict(set)
        self._def_blk2:dict[Block, set[UseDefItem]] = defaultdict(set)
        self._use_blk2:dict[Block, set[UseDefItem]] = defaultdict(set)

        self._use_stm2const:dict[IRStm, set[CONST]] = defaultdict(set)

    def add_var_def(self, scope: Scope, var: IRVariable, stm: IRStm):
        assert var.is_a(IRVariable) and stm.is_a(IRStm)
        qsyms:tuple[Symbol] = qualified_symbols(var, scope)
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._def_sym2[sym].add(item)
        self._def_qsym2[qsyms].add(item)
        self._def_var2[var].add(item)
        self._def_stm2[stm].add(item)
        self._def_blk2[stm.block].add(item)

    def remove_var_def(self, scope: Scope, var: IRVariable, stm: IRStm):
        assert var.is_a(IRVariable) and stm.is_a(IRStm)
        qsyms:tuple[Symbol] = qualified_symbols(var, scope)

        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._def_sym2[sym].discard(item)
        self._def_qsym2[qsyms].discard(item)
        self._def_var2[var].discard(item)
        self._def_stm2[stm].discard(item)
        self._def_blk2[stm.block].discard(item)

    def add_var_use(self, scope: Scope, var: IRVariable, stm: IRStm):
        assert var.is_a(IRVariable) and stm.is_a(IRStm)
        qsyms:tuple[Symbol] = qualified_symbols(var, scope)

        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._use_sym2[sym].add(item)
        self._use_qsym2[qsyms].add(item)
        self._use_var2[var].add(item)
        self._use_stm2[stm].add(item)
        self._use_blk2[stm.block].add(item)

    def remove_var_use(self, scope: Scope, var: IRVariable, stm: IRStm):
        assert var.is_a(IRVariable) and stm.is_a(IRStm)
        qsyms: tuple[Symbol] = qualified_symbols(var, scope)

        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._use_sym2[sym].discard(item)
        self._use_qsym2[qsyms].discard(item)
        self._use_var2[var].discard(item)
        self._use_stm2[stm].discard(item)
        self._use_blk2[stm.block].discard(item)

    def add_const_use(self, c: CONST, stm: IRStm):
        assert c.is_a(CONST) and stm.is_a(IRStm)
        self._use_stm2const[stm].add(c)

    def remove_const_use(self, c: CONST, stm: IRStm):
        assert c.is_a(CONST) and stm.is_a(IRStm)
        self._use_stm2const[stm].discard(c)

    def add_use(self, scope: Scope, v: CONST|IRVariable, stm: IRStm):
        if v.is_a(IRVariable):
            self.add_var_use(scope, v, stm)
        elif v.is_a(CONST):
            self.add_const_use(v, stm)
        else:
            assert False

    def remove_use(self, scope: Scope, v: CONST|IRVariable, stm: IRStm):
        if v.is_a(IRVariable):
            self.remove_var_use(scope, v, stm)
        elif v.is_a(CONST):
            self.remove_const_use(v, stm)
        else:
            assert False

    def remove_uses(self, scope: Scope, vs: list, stm: IRStm):
        for v in vs:
            self.remove_use(scope, v, stm)

    def remove_stm(self, scope: Scope, stm: IRStm):
        self.remove_uses(scope, list(self.get_vars_used_at(stm)), stm)
        for v in list(self.get_vars_defined_at(stm)):
            self.remove_var_def(scope, v, stm)

    def get_stms_defining(self, key: Symbol|IRVariable|tuple[Symbol]) -> set[IRStm]:
        if isinstance(key, Symbol):
            stms = set([item.stm for item in self._def_sym2[key]])
            return stms
        elif isinstance(key, IRVariable):
            stms = set([item.stm for item in self._def_var2[key]])
            return stms
        elif isinstance(key, tuple):
            stms = set([item.stm for item in self._def_qsym2[key]])
            return stms
        else:
            assert False

    def get_stms_using(self, key: Symbol|IRVariable|tuple[Symbol]) -> set[IRStm]:
        if isinstance(key, Symbol):
            stms = set([item.stm for item in self._use_sym2[key]])
            return stms
        elif isinstance(key, IRVariable):
            stms = set([item.stm for item in self._use_var2[key]])
            return stms
        elif isinstance(key, tuple):
            stms = set([item.stm for item in self._use_qsym2[key]])
            return stms
        else:
            assert False

    def get_blks_defining(self, sym: Symbol) -> set[Block]:
        blks = set([item.blk for item in self._def_sym2[sym]])
        return blks

    def get_blks_using(self, sym: Symbol) -> set[Block]:
        blks = set([item.blk for item in self._use_sym2[sym]])
        return blks

    def get_vars_defined_at(self, key: IRStm|Block) -> set[IRVariable]:
        if isinstance(key, IRStm):
            vars = set([item.var for item in self._def_stm2[key]])
            return vars
        elif isinstance(key, Block):
            vars = set([item.var for item in self._def_blk2[key]])
            return vars
        else:
            assert False

    def get_vars_used_at(self, key: IRStm|Block) -> set[IRVariable]:
        if isinstance(key, IRStm):
            vars = set([item.var for item in self._use_stm2[key]])
            return vars
        elif isinstance(key, Block):
            vars = set([item.var for item in self._use_blk2[key]])
            return vars
        else:
            assert False

    def get_consts_used_at(self, stm: IRStm) -> set[CONST]:
        return self._use_stm2const[stm]

    def get_syms_defined_at(self, key: IRStm|Block) -> set[Symbol]:
        if isinstance(key, IRStm):
            syms = set([item.sym for item in self._def_stm2[key]])
            return syms
        elif isinstance(key, Block):
            syms = set([item.sym for item in self._def_blk2[key]])
            return syms
        else:
            assert False

    def get_syms_used_at(self, key: IRStm|Block) -> set[Symbol]:
        if isinstance(key, IRStm):
            syms = set([item.sym for item in self._use_stm2[key]])
            return syms
        elif isinstance(key, Block):
            syms = set([item.sym for item in self._use_blk2[key]])
            return syms
        else:
            assert False

    def get_qsyms_defined_at(self, key: IRStm|Block) -> set[tuple[Symbol]]:
        if isinstance(key, IRStm):
            qsyms = set([item.qsym for item in self._def_stm2[key]])
            return qsyms
        elif isinstance(key, Block):
            qsyms = set([item.qsym for item in self._def_blk2[key]])
            return qsyms
        else:
            assert False

    def get_qsyms_used_at(self, key: IRStm|Block) -> set[tuple[Symbol]]:
        if isinstance(key, IRStm):
            qsyms = set([item.qsym for item in self._use_stm2[key]])
            return qsyms
        elif isinstance(key, Block):
            qsyms = set([item.qsym for item in self._use_blk2[key]])
            return qsyms
        else:
            assert False

    def get_all_def_syms(self):
        return self._def_sym2.keys()

    def get_all_use_syms(self):
        return self._use_sym2.keys()

    def get_all_vars(self):
        vs = list(self._def_var2.keys())
        vs.extend(self._use_var2.keys())
        return vs

    def get_qsym_block_dict_items(self):
        for qsym, items in self._def_qsym2.items():
            blks = set([item.blk for item in items])
            yield qsym, blks

    def __str__(self):
        s = ''
        s += '--------------------------------\n'
        s += 'statements that has symbol defs\n'
        for sym, items in self._def_sym2.items():
            s += f'{sym}\n'
            for item in items:
                s += f'    {item.stm}\n'
        s += '--------------------------------\n'
        s += 'blocks that has symbol defs\n'
        for sym, items in self._def_sym2.items():
            s += f'{sym}\n'
            for item in items:
                s += f'    {item.blk.name}\n'
        s += '--------------------------------\n'
        s += 'statements that has symbol uses\n'
        for sym, items in self._use_sym2.items():
            s += f'{sym}\n'
            for item in items:
                s += f'    {item.stm}\n'
        s += '--------------------------------\n'
        s += 'blocks that has symbol uses\n'
        for sym, items in self._use_sym2.items():
            s += f'{sym}\n'
            for item in items:
                s += f'    {item.blk.name}\n'
        return s

    def dump(self):
        logger.debug(self)


class UseDefDetector(IRVisitor):
    ADD = 0
    REMOVE = 1

    def __init__(self):
        super().__init__()
        self.table = UseDefTable()
        self.set_mode(UseDefDetector.ADD)

    def set_mode(self, mode):
        if mode == UseDefDetector.ADD:
            self.update_const_use = self.table.add_const_use
            self.update_var_def = self.table.add_var_def
            self.update_var_use = self.table.add_var_use
        else:
            self.update_const_use = self.table.remove_const_use
            self.update_var_def = self.table.remove_var_def
            self.update_var_use = self.table.remove_var_use

    def _process_scope_done(self, scope):
        scope.usedef = self.table

    def _process_block(self, block):
        for stm in block.stms:
            self.visit(stm)
        # Do not access to path_exp on usedef detection
        #if block.path_exp:
        #    self.visit(block.path_exp)

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

    def visit_CONST(self, ir):
        self.update_const_use(ir, self.current_stm)

    def visit_TEMP(self, ir):
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self.update_var_use(self.scope, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self.update_var_def(self.scope, ir, self.current_stm)
        else:
            assert False
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym_t = sym.typ
        for expr in typehelper.find_expr(sym_t):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            self.visit(expr)
            self.current_stm = old_stm

    def visit_ATTR(self, ir):
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self.update_var_use(self.scope, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self.update_var_def(self.scope, ir, self.current_stm)
        else:
            assert False
        self.visit(ir.exp)

        qsyms = qualified_symbols(ir, self.scope)
        attr_t = qsyms[-1].typ
        for expr in typehelper.find_expr(attr_t):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            self.visit(expr)
            self.current_stm = old_stm


class UseDefUpdater(object):
    def __init__(self, scope):
        self.adder = UseDefDetector()
        self.remover = UseDefDetector()
        self.adder.scope = scope
        self.adder.table = scope.usedef
        self.remover.scope = scope
        self.remover.table = scope.usedef
        self.adder.set_mode(UseDefDetector.ADD)
        self.remover.set_mode(UseDefDetector.REMOVE)

    def update(self, old_stm, new_stm):
        if old_stm:
            self.remover.visit(old_stm)
        if new_stm:
            self.adder.visit(new_stm)

