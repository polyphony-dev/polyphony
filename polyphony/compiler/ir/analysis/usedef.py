from collections import defaultdict
from dataclasses import dataclass
from ..irvisitor import IrVisitor
from ..ir import *
from ..irhelper import qualified_symbols


from ..block import Block
from ..symbol import Symbol
from ..scope import Scope
from ..types.type import Type
from ..types import typehelper
from logging import getLogger

logger = getLogger(__name__)


@dataclass(frozen=True, eq=False)
class UseDefItem:
    sym: Symbol
    qsym: tuple[Symbol | str, ...]
    var: IrVariable
    stm: IrStm
    blk: str  # block bid

    def __eq__(self, other):
        if not isinstance(other, UseDefItem):
            return NotImplemented
        return (self.sym is other.sym and
                self.qsym == other.qsym and
                self.var is other.var and
                self.stm is other.stm and
                self.blk == other.blk)

    def __hash__(self):
        return hash((id(self.sym), self.qsym, id(self.var), id(self.stm), self.blk))


class UseDefTable(object):
    def __init__(self):
        self._def_sym2: dict[Symbol, set[UseDefItem]] = defaultdict(set)
        self._use_sym2: dict[Symbol, set[UseDefItem]] = defaultdict(set)
        self._def_qsym2: dict[tuple[Symbol | str, ...], set[UseDefItem]] = defaultdict(set)
        self._use_qsym2: dict[tuple[Symbol | str, ...], set[UseDefItem]] = defaultdict(set)
        self._def_var2: dict[IrVariable, set[UseDefItem]] = defaultdict(set)
        self._use_var2: dict[IrVariable, set[UseDefItem]] = defaultdict(set)
        self._def_stm2: dict[IrStm, set[UseDefItem]] = defaultdict(set)
        self._use_stm2: dict[IrStm, set[UseDefItem]] = defaultdict(set)
        self._def_blk2: dict[str, set[UseDefItem]] = defaultdict(set)  # keyed by bid
        self._use_blk2: dict[str, set[UseDefItem]] = defaultdict(set)  # keyed by bid

        self._use_stm2Const: dict[IrStm, set[Const]] = defaultdict(set)

    def add_var_def(self, scope: Scope, var: IrVariable, stm: IrStm):
        assert isinstance(var, IrVariable) and isinstance(stm, IrStm)
        qsyms: tuple[Symbol | str, ...] = qualified_symbols(var, scope)
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
        qsyms: tuple[Symbol | str, ...] = qualified_symbols(var, scope)

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
        qsyms: tuple[Symbol | str, ...] = qualified_symbols(var, scope)

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
        qsyms: tuple[Symbol | str, ...] = qualified_symbols(var, scope)

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

    def replace_stm(self, old_stm: IrStm, new_stm: IrStm):
        """Migrate all def/use entries from old_stm to new_stm."""
        for item in list(self._def_stm2.get(old_stm, set())):
            self._def_sym2[item.sym].discard(item)
            self._def_qsym2[item.qsym].discard(item)
            self._def_var2[item.var].discard(item)
            self._def_stm2[old_stm].discard(item)
            self._def_blk2[item.blk].discard(item)
            new_item = UseDefItem(item.sym, item.qsym, item.var, new_stm, new_stm.block)
            self._def_sym2[new_item.sym].add(new_item)
            self._def_qsym2[new_item.qsym].add(new_item)
            self._def_var2[new_item.var].add(new_item)
            self._def_stm2[new_stm].add(new_item)
            self._def_blk2[new_item.blk].add(new_item)
        for item in list(self._use_stm2.get(old_stm, set())):
            self._use_sym2[item.sym].discard(item)
            self._use_qsym2[item.qsym].discard(item)
            self._use_var2[item.var].discard(item)
            self._use_stm2[old_stm].discard(item)
            self._use_blk2[item.blk].discard(item)
            new_item = UseDefItem(item.sym, item.qsym, item.var, new_stm, new_stm.block)
            self._use_sym2[new_item.sym].add(new_item)
            self._use_qsym2[new_item.qsym].add(new_item)
            self._use_var2[new_item.var].add(new_item)
            self._use_stm2[new_stm].add(new_item)
            self._use_blk2[new_item.blk].add(new_item)
        consts = self._use_stm2Const.pop(old_stm, set())
        if consts:
            self._use_stm2Const[new_stm].update(consts)

    def get_stms_defining(self, key: Symbol | IrVariable | tuple[Symbol | str, ...]) -> set[IrStm]:
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

    def get_stms_using(self, key: Symbol | IrVariable | tuple[Symbol | str, ...]) -> set[IrStm]:
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

    def get_blks_defining(self, sym: Symbol) -> set[str]:
        blks = set([item.blk for item in self._def_sym2[sym]])
        return blks

    def get_blks_using(self, sym: Symbol) -> set[str]:
        blks = set([item.blk for item in self._use_sym2[sym]])
        return blks

    def get_vars_defined_at(self, key: IrStm | Block) -> list[IrVariable]:
        if isinstance(key, IrStm):
            return [item.var for item in self._def_stm2[key]]
        elif isinstance(key, Block):
            return [item.var for item in self._def_blk2[key.bid]]
        else:
            assert False

    def get_vars_used_at(self, key: IrStm | Block) -> list[IrVariable]:
        if isinstance(key, IrStm):
            return [item.var for item in self._use_stm2[key]]
        elif isinstance(key, Block):
            return [item.var for item in self._use_blk2[key.bid]]
        else:
            assert False

    def get_consts_used_at(self, stm: IrStm) -> set[Const]:
        return self._use_stm2Const[stm]

    def get_syms_defined_at(self, key: IrStm | Block) -> set[Symbol]:
        if isinstance(key, IrStm):
            syms = set([item.sym for item in self._def_stm2[key]])
            return syms
        elif isinstance(key, Block):
            syms = set([item.sym for item in self._def_blk2[key.bid]])
            return syms
        else:
            assert False

    def get_syms_used_at(self, key: IrStm | Block) -> set[Symbol]:
        if isinstance(key, IrStm):
            syms = set([item.sym for item in self._use_stm2[key]])
            return syms
        elif isinstance(key, Block):
            syms = set([item.sym for item in self._use_blk2[key.bid]])
            return syms
        else:
            assert False

    def get_qsyms_defined_at(self, key: IrStm | Block) -> set[tuple[Symbol | str, ...]]:
        if isinstance(key, IrStm):
            qsyms = set([item.qsym for item in self._def_stm2[key]])
            return qsyms
        elif isinstance(key, Block):
            qsyms = set([item.qsym for item in self._def_blk2[key.bid]])
            return qsyms
        else:
            assert False

    def get_qsyms_used_at(self, key: IrStm | Block) -> set[tuple[Symbol | str, ...]]:
        if isinstance(key, IrStm):
            qsyms = set([item.qsym for item in self._use_stm2[key]])
            return qsyms
        elif isinstance(key, Block):
            qsyms = set([item.qsym for item in self._use_blk2[key.bid]])
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
                s += f"    {item.blk}\n"
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
                s += f"    {item.blk}\n"
        return s

    def dump(self):
        logger.debug(self)



class UseDefUpdater(object):
    """Incremental update handler for new IR."""

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


class UseDefDetector(IrVisitor):
    ADD = 0
    REMOVE = 1

    def __init__(self):
        super().__init__()
        self.table = UseDefTable()
        self.set_mode(UseDefDetector.ADD)

    def set_mode(self, mode):
        if mode == UseDefDetector.ADD:
            self._add_or_remove_def = self._add_def
            self._add_or_remove_use = self._add_use
            self._add_or_remove_Const = self._add_Const
        else:
            self._add_or_remove_def = self._remove_def
            self._add_or_remove_use = self._remove_use
            self._add_or_remove_Const = self._remove_Const

    def process(self, scope):  # type: ignore[override]
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
        from ..irhelper import qualified_symbols

        qsyms = qualified_symbols(ir, self.scope)
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self._add_or_remove_use(qsyms, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self._add_or_remove_def(qsyms, ir, self.current_stm)

    def visit_Attr(self, ir):
        from ..irhelper import qualified_symbols

        qsyms = qualified_symbols(ir, self.scope)
        if ir.ctx == Ctx.LOAD or ir.ctx == Ctx.CALL:
            self._add_or_remove_use(qsyms, ir, self.current_stm)
        elif ir.ctx == Ctx.STORE:
            self._add_or_remove_def(qsyms, ir, self.current_stm)
        self.visit(ir.exp)
