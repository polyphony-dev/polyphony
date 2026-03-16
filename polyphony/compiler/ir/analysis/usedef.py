from collections import defaultdict
from dataclasses import dataclass
from ..ir_visitor import IRVisitor, IrVisitor
from ..ir import *
from ..ir import IrStm as NewIrStm, IrVariable as NewIrVariable, Const as NewConst, Expr as NewExpr
from ..ir_helper import qualified_symbols as _old_qualified_symbols
from ..ir_helper import qualified_symbols as _new_qualified_symbols


def qualified_symbols(var, scope):
    """Dispatch to old or new qualified_symbols based on var type."""
    if isinstance(var, NewIrVariable):
        return _new_qualified_symbols(var, scope)
    return _old_qualified_symbols(var, scope)


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
    var: IrVariable
    stm: IrStm
    blk: Block


class UseDefTable(object):
    def __init__(self):
        self._def_sym2: dict[Symbol, set[UseDefItem]] = defaultdict(set)
        self._use_sym2: dict[Symbol, set[UseDefItem]] = defaultdict(set)
        self._def_qsym2: dict[tuple[Symbol], set[UseDefItem]] = defaultdict(set)
        self._use_qsym2: dict[tuple[Symbol], set[UseDefItem]] = defaultdict(set)
        self._def_var2: dict[IrVariable, set[UseDefItem]] = defaultdict(set)
        self._use_var2: dict[IrVariable, set[UseDefItem]] = defaultdict(set)
        self._def_stm2: dict[IrStm, set[UseDefItem]] = defaultdict(set)
        self._use_stm2: dict[IrStm, set[UseDefItem]] = defaultdict(set)
        self._def_blk2: dict[Block, set[UseDefItem]] = defaultdict(set)
        self._use_blk2: dict[Block, set[UseDefItem]] = defaultdict(set)

        self._use_stm2Const: dict[IrStm, set[Const]] = defaultdict(set)

    def add_var_def(self, scope: Scope, var: IrVariable, stm: IrStm):
        assert isinstance(var, IrVariable) and isinstance(stm, IrStm)
        qsyms: tuple[Symbol] = qualified_symbols(var, scope)
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)

        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._def_sym2[sym].add(item)
        self._def_qsym2[qsyms].add(item)
        self._def_var2[var].add(item)
        self._def_stm2[stm].add(item)
        self._def_blk2[stm.block].add(item)

    def remove_var_def(self, scope: Scope, var: IrVariable, stm: IrStm):
        assert isinstance(var, IrVariable) and isinstance(stm, IrStm)
        qsyms: tuple[Symbol] = qualified_symbols(var, scope)

        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._def_sym2[sym].discard(item)
        self._def_qsym2[qsyms].discard(item)
        self._def_var2[var].discard(item)
        self._def_stm2[stm].discard(item)
        self._def_blk2[stm.block].discard(item)

    def add_var_use(self, scope: Scope, var: IrVariable, stm: IrStm):
        assert isinstance(var, IrVariable) and isinstance(stm, IrStm)
        qsyms: tuple[Symbol] = qualified_symbols(var, scope)

        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._use_sym2[sym].add(item)
        self._use_qsym2[qsyms].add(item)
        self._use_var2[var].add(item)
        self._use_stm2[stm].add(item)
        self._use_blk2[stm.block].add(item)

    def remove_var_use(self, scope: Scope, var: IrVariable, stm: IrStm):
        assert isinstance(var, IrVariable) and isinstance(stm, IrStm)
        qsyms: tuple[Symbol] = qualified_symbols(var, scope)

        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self._use_sym2[sym].discard(item)
        self._use_qsym2[qsyms].discard(item)
        self._use_var2[var].discard(item)
        self._use_stm2[stm].discard(item)
        self._use_blk2[stm.block].discard(item)

    def add_Const_use(self, c: Const, stm: IrStm):
        assert isinstance(stm, IrStm)
        self._use_stm2Const[stm].add(c)

    def remove_Const_use(self, c: Const, stm: IrStm):
        assert isinstance(stm, IrStm)
        self._use_stm2Const[stm].discard(c)

    def add_use(self, scope: Scope, v: Const | IrVariable, stm: IrStm):
        if isinstance(v, IrVariable):
            self.add_var_use(scope, v, stm)
        elif isinstance(v, Const):
            self.add_Const_use(v, stm)
        else:
            assert False

    def remove_use(self, scope: Scope, v: Const | IrVariable, stm: IrStm):
        if isinstance(v, IrVariable):
            self.remove_var_use(scope, v, stm)
        elif isinstance(v, Const):
            self.remove_Const_use(v, stm)
        else:
            assert False

    def remove_uses(self, scope: Scope, vs: list, stm: IrStm):
        for v in vs:
            self.remove_use(scope, v, stm)

    def remove_stm(self, scope: Scope, stm: IrStm):
        self.remove_uses(scope, list(self.get_vars_used_at(stm)), stm)
        for v in list(self.get_vars_defined_at(stm)):
            self.remove_var_def(scope, v, stm)

    def get_stms_defining(self, key: Symbol | IrVariable | tuple[Symbol]) -> set[IrStm]:
        if isinstance(key, Symbol):
            stms = set([item.stm for item in self._def_sym2[key]])
            return stms
        elif isinstance(key, IrVariable):
            stms = set([item.stm for item in self._def_var2[key]])
            return stms
        elif isinstance(key, tuple):
            stms = set([item.stm for item in self._def_qsym2[key]])
            return stms
        else:
            assert False

    def get_stms_using(self, key: Symbol | IrVariable | tuple[Symbol]) -> set[IrStm]:
        if isinstance(key, Symbol):
            stms = set([item.stm for item in self._use_sym2[key]])
            return stms
        elif isinstance(key, IrVariable):
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

    def get_vars_defined_at(self, key: IrStm | Block) -> set[IrVariable]:
        if isinstance(key, IrStm):
            vars = set([item.var for item in self._def_stm2[key]])
            return vars
        elif isinstance(key, Block):
            vars = set([item.var for item in self._def_blk2[key]])
            return vars
        else:
            assert False

    def get_vars_used_at(self, key: IrStm | Block) -> set[IrVariable]:
        if isinstance(key, IrStm):
            vars = set([item.var for item in self._use_stm2[key]])
            return vars
        elif isinstance(key, Block):
            vars = set([item.var for item in self._use_blk2[key]])
            return vars
        else:
            assert False

    def get_consts_used_at(self, stm: IrStm) -> set[Const]:
        return self._use_stm2Const[stm]

    def get_syms_defined_at(self, key: IrStm | Block) -> set[Symbol]:
        if isinstance(key, IrStm):
            syms = set([item.sym for item in self._def_stm2[key]])
            return syms
        elif isinstance(key, Block):
            syms = set([item.sym for item in self._def_blk2[key]])
            return syms
        else:
            assert False

    def get_syms_used_at(self, key: IrStm | Block) -> set[Symbol]:
        if isinstance(key, IrStm):
            syms = set([item.sym for item in self._use_stm2[key]])
            return syms
        elif isinstance(key, Block):
            syms = set([item.sym for item in self._use_blk2[key]])
            return syms
        else:
            assert False

    def get_qsyms_defined_at(self, key: IrStm | Block) -> set[tuple[Symbol]]:
        if isinstance(key, IrStm):
            qsyms = set([item.qsym for item in self._def_stm2[key]])
            return qsyms
        elif isinstance(key, Block):
            qsyms = set([item.qsym for item in self._def_blk2[key]])
            return qsyms
        else:
            assert False

    def get_qsyms_used_at(self, key: IrStm | Block) -> set[tuple[Symbol]]:
        if isinstance(key, IrStm):
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
        s = ""
        s += "--------------------------------\n"
        s += "statements that has symbol defs\n"
        for sym, items in self._def_sym2.items():
            s += f"{sym}\n"
            for item in items:
                s += f"    {item.stm}\n"
        s += "--------------------------------\n"
        s += "blocks that has symbol defs\n"
        for sym, items in self._def_sym2.items():
            s += f"{sym}\n"
            for item in items:
                s += f"    {item.blk.name}\n"
        s += "--------------------------------\n"
        s += "statements that has symbol uses\n"
        for sym, items in self._use_sym2.items():
            s += f"{sym}\n"
            for item in items:
                s += f"    {item.stm}\n"
        s += "--------------------------------\n"
        s += "blocks that has symbol uses\n"
        for sym, items in self._use_sym2.items():
            s += f"{sym}\n"
            for item in items:
                s += f"    {item.blk.name}\n"
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
            self.update_Const_use = self.table.add_Const_use
            self.update_var_def = self.table.add_var_def
            self.update_var_use = self.table.add_var_use
        else:
            self.update_Const_use = self.table.remove_Const_use
            self.update_var_def = self.table.remove_var_def
            self.update_var_use = self.table.remove_var_use

    def process(self, scope):
        super().process(scope)
        return self.table

    def _process_block(self, block):
        for stm in block.stms:
            self.visit(stm)
        # Do not access to path_exp on usedef detection
        # if block.path_exp:
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

    def visit_Const(self, ir):
        self.update_Const_use(ir, self.current_stm)

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
        for expr_t in typehelper.find_expr(sym_t):
            expr = expr_t.expr
            assert isinstance(expr, NewExpr)
            self.visit_with_context(expr_t.scope, expr)

    def visit_ATTR(self, ir):
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self.update_var_use(self.scope, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self.update_var_def(self.scope, ir, self.current_stm)
        else:
            assert False
        self.visit(ir.exp)

        attr = qualified_symbols(ir, self.scope)[-1]
        assert isinstance(attr, Symbol)
        for expr_t in typehelper.find_expr(attr.typ):
            expr = expr_t.expr
            assert isinstance(expr, NewExpr)
            self.visit_with_context(expr_t.scope, expr)

    def visit_with_context(self, scope: Scope, IrStm: IrStm):
        old_scope = self.scope
        old_stm = self.current_stm
        self.scope = scope
        self.current_stm = IrStm
        self.visit(IrStm)
        self.scope = old_scope
        self.current_stm = old_stm


class UseDefUpdater(object):
    def __init__(self, scope, usedef):
        self.adder = UseDefDetector()
        self.remover = UseDefDetector()
        self.adder.scope = scope
        self.adder.table = usedef
        self.remover.scope = scope
        self.remover.table = usedef
        self.adder.set_mode(UseDefDetector.ADD)
        self.remover.set_mode(UseDefDetector.REMOVE)

    def update(self, old_stm, new_stm):
        if old_stm:
            self.remover.visit(old_stm)
        if new_stm:
            self.adder.visit(new_stm)


class NewUseDefUpdater(object):
    """Incremental update handler for new IR."""

    def __init__(self, scope, usedef):
        self.adder = NewUseDefDetector()
        self.remover = NewUseDefDetector()
        self.adder.scope = scope
        self.adder.table = usedef
        self.remover.scope = scope
        self.remover.table = usedef
        self.adder.set_mode(NewUseDefDetector.ADD)
        self.remover.set_mode(NewUseDefDetector.REMOVE)

    def update(self, old_stm, new_stm):
        if old_stm:
            self.remover.visit(old_stm)
        if new_stm:
            self.adder.visit(new_stm)


class NewUseDefDetector(IrVisitor):
    ADD = 0
    REMOVE = 1

    def __init__(self):
        super().__init__()
        self.table = UseDefTable()
        self.set_mode(NewUseDefDetector.ADD)

    def set_mode(self, mode):
        if mode == NewUseDefDetector.ADD:
            self._add_or_remove_def = self._add_def
            self._add_or_remove_use = self._add_use
            self._add_or_remove_Const = self._add_Const
        else:
            self._add_or_remove_def = self._remove_def
            self._add_or_remove_use = self._remove_use
            self._add_or_remove_Const = self._remove_Const

    def process(self, scope):
        super().process(scope)
        return self.table

    def _process_block(self, block):
        for stm in block.stms:
            self.visit(stm)

    # --- Low-level table operations with pre-resolved qsyms ---

    def _add_def(self, qsyms, var, stm):
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self.table._def_sym2[sym].add(item)
        self.table._def_qsym2[qsyms].add(item)
        self.table._def_var2[var].add(item)
        self.table._def_stm2[stm].add(item)
        self.table._def_blk2[stm.block].add(item)

    def _remove_def(self, qsyms, var, stm):
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self.table._def_sym2[sym].discard(item)
        self.table._def_qsym2[qsyms].discard(item)
        self.table._def_var2[var].discard(item)
        self.table._def_stm2[stm].discard(item)
        self.table._def_blk2[stm.block].discard(item)

    def _add_use(self, qsyms, var, stm):
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self.table._use_sym2[sym].add(item)
        self.table._use_qsym2[qsyms].add(item)
        self.table._use_var2[var].add(item)
        self.table._use_stm2[stm].add(item)
        self.table._use_blk2[stm.block].add(item)

    def _remove_use(self, qsyms, var, stm):
        sym = qsyms[-1]
        assert isinstance(sym, Symbol)
        item = UseDefItem(sym, qsyms, var, stm, stm.block)
        self.table._use_sym2[sym].discard(item)
        self.table._use_qsym2[qsyms].discard(item)
        self.table._use_var2[var].discard(item)
        self.table._use_stm2[stm].discard(item)
        self.table._use_blk2[stm.block].discard(item)

    def _add_Const(self, c, stm):
        self.table._use_stm2Const[stm].add(c)

    def _remove_Const(self, c, stm):
        self.table._use_stm2Const[stm].discard(c)

    # --- Visitor methods ---

    def _visit_args(self, args, kwargs):
        for _, arg in args:
            self.visit(arg)

    def visit_Call(self, ir):
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_SysCall(self, ir):
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_New(self, ir):
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_Const(self, ir):
        self._add_or_remove_Const(ir, self.current_stm)

    def visit_Temp(self, ir):
        from ..ir_helper import qualified_symbols

        qsyms = qualified_symbols(ir, self.scope)
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self._add_or_remove_use(qsyms, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self._add_or_remove_def(qsyms, ir, self.current_stm)

    def visit_Attr(self, ir):
        from ..ir_helper import qualified_symbols

        qsyms = qualified_symbols(ir, self.scope)
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self._add_or_remove_use(qsyms, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self._add_or_remove_def(qsyms, ir, self.current_stm)
        self.visit(ir.exp)
