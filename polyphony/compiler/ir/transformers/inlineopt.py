"""Inline optimization passes using new IR (ir.py).

All passes operate directly on block.stms which contains unified IR types.
--

Classes:
  ObjectHierarchyCopier - Copy object hierarchy for inlined objects
  FlattenFieldAccess - Flatten nested attribute access chains
  InlineOpt - Inline function/method/ctor calls
  FlattenModule - Flatten module method calls
  CallCollector - Collect Call/New nodes from stms
  AllVariableCollector - Collect all variables in stms
  NonlocalVariableCollector - Collect free variables in stms
  LocalVariableCollector - Collect local variables in stms
  IrReplacer - Replace variables in stms based on a symbol map
"""

from collections import defaultdict, deque
import dataclasses
from typing import cast
from ..ir import (
    Ir,
    IrExp,
    IrStm,
    IrVariable,
    IrNameExp,
    IrCallable,
    Move,
    Attr,
    Temp,
    Ctx,
    Expr,
    SysCall,
    Const,
    Array,
    UnOp,
    Jump,
    Ret,
)
from ..types.exprtype import ExprType
from .varreplacer import replace_exprtype_in_typ
from ..irvisitor import IrVisitor, IrTransformer
from ..irhelper import qualified_symbols, irexp_type, qsym2var
from ..analysis.usedef import UseDefDetector
from ..symbol import Symbol
from ..scope import Scope
from ..types import typehelper
from ..block import Block
from ..synth import merge_synth_params
from ...common.env import env
import logging

logger = logging.getLogger()

type ReplaceMap = dict[Symbol, IrExp]
type CallStmPair = tuple[IrCallable, IrStm]


class CallerScope(Scope):
    pass


class CalleeScope(Scope):
    pass


type CallsDict = dict[CalleeScope, list[CallStmPair]]
type Callgraph = dict[CallerScope, CallsDict]


# ============================================================
# Helper visitors for InlineOpt
# ============================================================


class CallCollector(IrVisitor):
    """Collect Call/New nodes and their containing statements from block.stms."""

    def __init__(self, calls: CallsDict):
        self.calls = calls

    def visit_Call(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        self.calls[callee_scope].append((ir, self.current_stm))

    def visit_New(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        assert callee_scope.is_class()
        ctor = callee_scope.find_ctor()
        assert ctor
        self.calls[ctor].append((ir, self.current_stm))


class AllVariableCollector(IrVisitor):
    """Collect all named variables that have symbols in scope."""

    def __init__(self):
        self.all_vars = []

    def process(self, scope):  # type: ignore[override]
        super().process(scope)
        return self.all_vars

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        if sym:
            self.all_vars.append(ir)

    def visit_Attr(self, ir):
        self.visit(ir.exp)


class NonlocalVariableCollector(IrVisitor):
    """Collect variables whose symbol is defined outside the current scope."""

    def __init__(self):
        self.nonlocal_vars = []

    def process(self, scope):  # type: ignore[override]
        super().process(scope)
        return self.nonlocal_vars

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        if sym and sym.scope is not self.scope:
            self.nonlocal_vars.append(ir)

    def visit_Attr(self, ir):
        self.visit(ir.exp)


class LocalVariableCollector(IrVisitor):
    """Collect variables whose symbol is defined in the current scope."""

    def __init__(self):
        self.local_vars = []

    def process(self, scope):  # type: ignore[override]
        super().process(scope)
        return self.local_vars

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        if sym and sym.scope is self.scope:
            self.local_vars.append(ir)

    def visit_Attr(self, ir):
        self.visit(ir.exp)


class IrReplacer(IrTransformer):
    """Replace variables in block.stms based on a symbol->expression map."""

    def __init__(self, replace_map: ReplaceMap):
        self.replace_map = replace_map

    def process(self, scope, entry_block):  # type: ignore[override]
        self.scope = scope
        for blk in entry_block.traverse():
            self._process_block(blk)

    def visit_Temp(self, ir):
        ret_ir = ir
        sym = self.scope.find_sym(ir.name)
        assert sym
        if sym in self.replace_map:
            replacement = self.replace_map[sym]
            if isinstance(replacement, Ir):
                ret_ir = replacement.clone(ctx=ir.ctx)
            else:
                ret_ir = replacement
        if isinstance(ret_ir, IrVariable):
            ret_sym = qualified_symbols(ret_ir, self.scope)[-1]
            if isinstance(ret_sym, Symbol):
                for expr_t in typehelper.find_expr(ret_sym.typ):
                    self._visit_expr_type(expr_t)
        return ret_ir

    def visit_Attr(self, ir):
        exp = self.visit(ir.exp)
        if exp and exp is not ir.exp:
            ir = ir.model_copy(update={"exp": exp})
        sym = qualified_symbols(ir, self.scope)[-1]
        if isinstance(sym, Symbol):
            for expr_t in typehelper.find_expr(sym.typ):
                self._visit_expr_type(expr_t)
        return ir

    def _visit_expr_type(self, expr_t):
        """Visit ExprType.expr (new IR Expr) in place."""
        expr = expr_t.expr
        assert isinstance(expr, Expr)
        self.visit_with_context(expr_t.scope, expr)

    def visit_with_context(self, scope: Scope, irstm: IrStm):
        old_scope = self.scope
        old_stm = self.current_stm
        self.scope = scope
        self.current_stm = irstm
        self.visit(irstm)
        self.new_stms.pop()
        self.scope = old_scope
        self.current_stm = old_stm

    def visit_Array(self, ir):
        new_repeat = self.visit(ir.repeat) if ir.repeat is not None else ir.repeat
        new_items = [self.visit(item) for item in ir.items]
        repeat_changed = new_repeat is not ir.repeat
        items_changed = any(ni is not oi for ni, oi in zip(new_items, ir.items))
        if not repeat_changed and not items_changed:
            return ir
        return ir.model_copy(update={'repeat': new_repeat, 'items': tuple(new_items)})


# ============================================================
# ObjectHierarchyCopier
# ============================================================


class ObjectHierarchyCopier(object):
    def __init__(self):
        pass

    def _is_inlining_object(self, ir):
        if isinstance(ir, IrVariable):
            qsym = qualified_symbols(ir, self.scope)
            sym = qsym[-1]
            assert isinstance(sym, Symbol)
            return not sym.is_param() and sym.typ.is_object() and sym.typ.scope and not sym.typ.scope.is_module()
        return False

    def _is_object_copy(self, mov):
        return self._is_inlining_object(mov.src) and self._is_inlining_object(mov.dst)

    def _collect_object_copy(self):
        copies = []
        for block in self.scope.traverse_blocks():
            moves = [stm for stm in block.stms if isinstance(stm, Move)]
            copies.extend([stm for stm in moves if self._is_object_copy(stm)])
        return copies

    def process(self, scope):  # type: ignore[override]
        self.scope = scope
        copies = self._collect_object_copy()
        worklist = deque(copies)
        while worklist:
            cp = worklist.popleft()
            src_sym = qualified_symbols(cp.src, self.scope)[-1]
            dst_sym = qualified_symbols(cp.dst, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            assert isinstance(dst_sym, Symbol)
            src_typ = src_sym.typ
            dst_typ = dst_sym.typ
            assert src_typ.has_scope()
            assert dst_typ.has_scope()
            class_scope = src_typ.scope
            assert class_scope.is_assignable(dst_typ.scope)
            for sym in class_scope.class_fields().values():
                if not sym.typ.is_object():
                    continue
                new_dst = Attr(
                    name=sym.name,
                    exp=cp.dst.model_copy(deep=True),
                    attr=sym,
                    ctx=Ctx.STORE,
                )
                new_src = Attr(
                    name=sym.name,
                    exp=cp.src.model_copy(deep=True),
                    attr=sym,
                    ctx=Ctx.LOAD,
                )
                new_cp = Move(dst=new_dst, src=new_src, loc=cp.loc, block=cp.block)
                cp_blk = self.scope.find_block(cp.block)
                cp_idx = cp_blk.stms.index(cp)
                cp_blk.stms.insert(cp_idx + 1, new_cp)
                if sym.typ.is_object():
                    worklist.append(new_cp)


# ============================================================
# FlattenFieldAccess
# ============================================================


class FlattenFieldAccess(IrTransformer):
    """Flatten nested attribute access chains using new IR.

    Converts e.g. self.obj.field -> self_obj_field by creating
    flattened symbols in the appropriate scope.
    """

    def _make_flatname(self, qsym):
        qnames = [sym.name for sym in qsym if sym.name != env.self_name]
        return "_".join(qnames)

    def _make_flatten_qsym(self, ir):
        assert isinstance(ir, Attr)
        flatname = None
        qsyms = cast(tuple[Symbol, ...], qualified_symbols(ir, self.scope))
        head = qsyms[0]
        inlining_scope = head.scope
        if qsyms[-1].typ.is_function():
            tail = (qsyms[-1],)
            qsyms = qsyms[:-1]
        else:
            tail = tuple()

        ancestor = qsyms[-1]
        for i, sym in enumerate(qsyms):
            if sym.typ.is_object() and not sym.is_subobject() and sym.typ.scope.is_module():
                flatname = self._make_flatname(qsyms[i + 1 :])
                head = qsyms[: i + 1]
                scope = sym.typ.scope
                break
        else:
            flatname = self._make_flatname(qsyms)
            head = tuple()
            scope = inlining_scope
        if flatname:
            if scope.has_sym(flatname):
                flatsym = scope.find_sym(flatname)
            else:
                tags = set()
                qsym = cast(tuple[Symbol, ...], qualified_symbols(ir, self.scope))
                for sym in qsym:
                    tags |= sym.tags
                flatsym = scope.add_sym(flatname, tags, typ=ancestor.typ)
                env.origin_registry.set_sym_origin(flatsym, ancestor)
                flatsym.add_tag("flattened")
            return head + (flatsym,) + tail
        else:
            return head + tail

    def _make_new_attr(self, qsym, ir):
        """Build a new Attr/Temp chain from the flattened qsym."""

        def context(i):
            return ir.ctx if i == len(qsym) - 1 else Ctx.LOAD

        newir = Temp(name=qsym[0].name, ctx=context(0))
        for i in range(1, len(qsym)):
            newir = Attr(name=qsym[i].name, exp=newir, attr=qsym[i], ctx=context(i))
        assert newir.ctx == ir.ctx
        return newir

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        for expr_t in typehelper.find_expr(sym.typ):
            self._visit_expr_type_flatten(expr_t)
        return ir

    def visit_Attr(self, ir):
        qsym = cast(tuple[Symbol, ...], qualified_symbols(ir, self.scope))
        sym = qsym[-1]
        assert isinstance(sym, Symbol)
        for expr_t in typehelper.find_expr(sym.typ):
            self._visit_expr_type_flatten(expr_t)

        # Don't flatten use of the other instance in the class except module
        if self.scope.is_method():
            if self.scope.parent.is_module():
                pass
            else:
                return ir
        receiver_t = qsym[-2].typ
        if not receiver_t.is_object():
            return ir
        object_scope = receiver_t.scope
        if object_scope.is_module():
            return ir
        if object_scope.is_port():
            return ir

        qsym = self._make_flatten_qsym(ir)
        newattr = self._make_new_attr(qsym, ir)
        return newattr

    def _visit_expr_type_flatten(self, expr_t):
        """Visit ExprType.expr (new IR Expr) using a temporary FlattenFieldAccess pass."""
        expr = expr_t.expr
        assert isinstance(expr, Expr)
        # Create a temporary transformer to visit the expression
        tmp = _FlattenFieldAccessForExprType()
        tmp.scope = expr_t.scope
        tmp.current_stm = expr
        tmp.new_stms = []
        tmp.visit(expr)
        # Discard new_stms since we only need in-place mutations

    # Backward compat for old FlattenFieldAccess references
    def _make_new_ATTR(self, qsym, ir):
        return self._make_new_attr(qsym, ir)


class _FlattenFieldAccessForExprType(IrTransformer):
    """Helper transformer for visiting ExprType expressions with flatten logic.

    Applies the same flattening rules as FlattenFieldAccess but on a single
    expression rather than traversing all blocks.
    """

    def _make_flatname(self, qsym):
        qnames = [sym.name for sym in qsym if sym.name != env.self_name]
        return "_".join(qnames)

    def _make_flatten_qsym(self, ir):
        assert isinstance(ir, Attr)
        flatname = None
        qsyms = cast(tuple[Symbol, ...], qualified_symbols(ir, self.scope))
        head = qsyms[0]
        inlining_scope = head.scope
        if qsyms[-1].typ.is_function():
            tail = (qsyms[-1],)
            qsyms = qsyms[:-1]
        else:
            tail = tuple()
        ancestor = qsyms[-1]
        for i, sym in enumerate(qsyms):
            if sym.typ.is_object() and not sym.is_subobject() and sym.typ.scope.is_module():
                flatname = self._make_flatname(qsyms[i + 1 :])
                head = qsyms[: i + 1]
                scope = sym.typ.scope
                break
        else:
            flatname = self._make_flatname(qsyms)
            head = tuple()
            scope = inlining_scope
        if flatname:
            if scope.has_sym(flatname):
                flatsym = scope.find_sym(flatname)
            else:
                tags = set()
                qsym = cast(tuple[Symbol, ...], qualified_symbols(ir, self.scope))
                for sym in qsym:
                    tags |= sym.tags
                flatsym = scope.add_sym(flatname, tags, typ=ancestor.typ)
                env.origin_registry.set_sym_origin(flatsym, ancestor)
                flatsym.add_tag("flattened")
            return head + (flatsym,) + tail
        else:
            return head + tail

    def _make_new_attr(self, qsym, ir):
        def context(i):
            return ir.ctx if i == len(qsym) - 1 else Ctx.LOAD

        newir = Temp(name=qsym[0].name, ctx=context(0))
        for i in range(1, len(qsym)):
            newir = Attr(name=qsym[i].name, exp=newir, attr=qsym[i], ctx=context(i))
        assert newir.ctx == ir.ctx
        return newir

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        for expr_t in typehelper.find_expr(sym.typ):
            expr = expr_t.expr
            assert isinstance(expr, Expr)
            old_scope = self.scope
            self.scope = expr_t.scope
            self.visit(expr)
            self.new_stms.pop()
            self.scope = old_scope
        return ir

    def visit_Attr(self, ir):
        qsym = cast(tuple[Symbol, ...], qualified_symbols(ir, self.scope))
        sym = qsym[-1]
        assert isinstance(sym, Symbol)
        for expr_t in typehelper.find_expr(sym.typ):
            expr = expr_t.expr
            assert isinstance(expr, Expr)
            old_scope = self.scope
            self.scope = expr_t.scope
            self.visit(expr)
            self.new_stms.pop()
            self.scope = old_scope
        if self.scope.is_method():
            if self.scope.parent.is_module():
                pass
            else:
                return ir
        receiver_t = qsym[-2].typ
        if not receiver_t.is_object():
            return ir
        object_scope = receiver_t.scope
        if object_scope.is_module():
            return ir
        if object_scope.is_port():
            return ir
        qsym = self._make_flatten_qsym(ir)
        newattr = self._make_new_attr(qsym, ir)
        return newattr


# ============================================================
# _SymbolRenamer - Functional symbol renamer for inline
# ============================================================


class _SymbolRenamer(IrTransformer):
    """Rename IrNameExp.name values in an IR tree based on name_map."""

    def __init__(self, name_map: dict[str, str]):
        super().__init__()
        self.name_map = name_map

    def visit_Temp(self, ir):
        new_name = self.name_map.get(ir.name)
        if new_name is None:
            return ir
        return ir.model_copy(update={'name': new_name})

    def _process_recursive(self, scope):
        self.process(scope)
        for child in scope.children:
            # Exclude names locally defined in the child scope to avoid
            # renaming variables that shadow the callee-level symbols.
            child_map = {old: new for old, new in self.name_map.items()
                         if not child.has_sym(old)}
            if child_map:
                _SymbolRenamer(child_map)._process_recursive(child)


# ============================================================
# InlineOpt - Main inline optimization
# ============================================================


class InlineOpt(object):
    """Inline optimization operating directly on block.stms (unified IR).

    Builds a call graph, processes leaf callees first, inlines function bodies
    into callers by cloning callee blocks and merging them into the caller's
    block structure.
    """

    inline_counts = 0

    def process_scopes(self, scopes):
        from .typeprop import TypePropagation

        self._new_scopes = []
        while True:
            call_graph: Callgraph = self._build_call_graph(scopes)
            callers = set()
            closure_callers: set[Scope] = set()
            restart = False
            while call_graph:
                leaf = self._pop_leaf(call_graph)
                if not leaf:
                    continue
                caller, callee, call_irs = leaf
                if callee.is_testbench():
                    continue
                if caller.is_testbench() and callee.is_function_module():
                    continue
                if caller.is_testbench() and callee.is_ctor() and callee.parent.is_module():
                    continue
                if caller.is_namespace() and callee.is_method():
                    continue
                ret = self._inlining(caller, callee, call_irs)
                logger.debug(f"inlined {callee.name} on {caller.name}")
                callers.add(caller)
                if not ret:
                    # Closure was merged — need typeprop on this caller only,
                    # then rebuild call graph and continue.
                    closure_callers.add(caller)
                    restart = True
                    break
            for c in callers:
                self._reduce_useless_move(c)
            if restart:
                # Run TypePropagation only on the affected callers and their new closures
                affected: list[Scope] = list(closure_callers)
                for s in self._new_scopes:
                    if s not in affected:
                        affected.append(s)
                TypePropagation(is_strict=False).process_scopes(affected)
                scopes = [s for s in scopes if s.name in env.scopes]
                continue
            break
        return self._new_scopes

    def _build_call_graph(self, scopes: list[Scope]) -> Callgraph:
        call_graph: Callgraph = {}
        for scope in scopes:
            self._build_call_graph_rec(cast(CallerScope, scope), call_graph)
        return call_graph

    def _build_call_graph_rec(self, caller: CallerScope, call_graph: Callgraph):
        if caller in call_graph:
            return
        calls: CallsDict = defaultdict(list)
        collector = CallCollector(calls)
        collector.process(caller)
        if calls:
            call_graph[caller] = calls
            for callee in calls.keys():
                self._build_call_graph_rec(cast(CallerScope, callee), call_graph)

    def _pop_leaf(self, call_graph: Callgraph) -> tuple[CallerScope, CalleeScope, list[CallStmPair]] | None:
        for caller, calls in call_graph.copy().items():
            for callee in calls.copy().keys():
                if callee not in call_graph:
                    call_irs = calls.pop(callee)
                    if not calls:
                        call_graph.pop(caller)
                    if callee.is_lib() or callee.is_pure():
                        continue
                    return caller, callee, call_irs
        return None

    def _make_replace_args_map(self, callee: CalleeScope, call: IrCallable) -> ReplaceMap:
        arg_map: ReplaceMap = {}
        for i, (param, defval) in enumerate(zip(callee.param_symbols(), callee.param_default_values())):  # type: ignore[arg-type]
            if len(call.args) > i:
                _, arg = call.args[i]
            else:
                arg = cast(IrExp, defval)
            if isinstance(arg, (Temp, Attr, Const, UnOp)):
                arg_map[param] = arg
            else:
                assert False, "CALL is not quadruple form"
        return arg_map

    def _make_replace_self_obj_map(
        self, callee: CalleeScope, call: IrCallable, call_stm: IrStm, caller: CallerScope
    ) -> ReplaceMap:
        self_map: ReplaceMap = {}
        callee_self = callee.find_sym(env.self_name)
        assert callee_self
        if callee.is_ctor():
            assert not callee.is_returnable()
            if isinstance(call_stm, Move):
                assert call_stm.src == call
                qsym = cast(tuple[Symbol, ...], qualified_symbols(cast(IrNameExp, call_stm.dst), caller))
                if callee_self.is_free():
                    qsym[0].add_tag("free")
                assert all(isinstance(sym, Symbol) for sym in qsym)
                self_map[callee_self] = qsym2var(qsym, Ctx.LOAD)
            else:
                logger.error(f"cannot inline {callee.name} because of statement is not MOVE")
        else:
            assert isinstance(call.func, Attr)
            receiver_sym = cast(tuple[Symbol, ...], qualified_symbols(cast(IrNameExp, call.func.exp), caller))
            if callee_self.is_free():
                receiver_sym[0].add_tag("free")
            self_map[callee_self] = qsym2var(receiver_sym, Ctx.LOAD)
        return self_map

    def _import_nonlocal_symbols(self, callee: CalleeScope, caller: CallerScope):
        callee_name_exps = NonlocalVariableCollector().process(callee)
        for name_exp in callee_name_exps:
            sym = callee.find_sym(name_exp.name)
            if caller.find_sym(name_exp.name) is sym:
                continue
            assert sym is not None
            callee.import_sym(sym, sym.name)

    def _resolve_free_var_constants(self, callee: CalleeScope) -> ReplaceMap:
        """Resolve free variables that are constants in the enclosing scope.

        When inlining a lambda/closure, free variables that have constant
        definitions in the enclosing scope should be replaced with their
        constant values.
        """
        replace_map: ReplaceMap = {}
        if not callee.parent:
            return replace_map
        parent = callee.parent
        parent_usedef = UseDefDetector().process(parent)
        for sym in list(callee.symbols.values()):
            if not sym.is_free():
                continue
            # Check if the symbol has a single constant definition in parent
            defs = parent_usedef._def_sym2.get(sym, set())
            if len(defs) == 1:
                def_item = next(iter(defs))
                stm = def_item.stm
                if isinstance(stm, Move) and isinstance(stm.src, (Const, Array)):
                    replace_map[sym] = stm.src
        return replace_map

    def _rename(self, callee: CalleeScope, caller: CallerScope):
        def make_unique_name(scopes: list[Scope], name: str) -> str:
            new_name = name
            count = 0
            for s in scopes:
                while s.find_sym(new_name):
                    new_name = f"{name}_{count}"
                    count += 1
            return new_name

        # Phase 1: build name_map and rename callee symbols
        name_map: dict[str, str] = {}
        for callee_sym in list(callee.symbols.values()):
            if callee_sym.is_self():
                continue
            if callee_sym.is_builtin():
                continue
            caller_sym = caller.find_sym(callee_sym.name)
            if not caller_sym or callee_sym is caller_sym:
                continue
            new_name = make_unique_name([caller, callee], callee_sym.name)
            old_name = callee_sym.name
            if callee_sym.scope is callee:
                callee.rename_sym(callee_sym.name, new_name)
            else:
                callee.rename_sym_asname(callee_sym.name, new_name)
            name_map[old_name] = new_name
            if callee_sym.is_typevar():
                self._rename_type_expr_var(callee, old_name, new_name)
        # Phase 2: apply renames to callee IR tree (including child scopes)
        if name_map:
            _SymbolRenamer(name_map)._process_recursive(callee)

    def _merge_symbols(self, callee: CalleeScope, caller: CallerScope):
        callee_name_exps = AllVariableCollector().process(callee)
        callee_names = sorted(set([name_exp.name for name_exp in callee_name_exps]))
        typevars = set()
        for name in callee_names:
            sym = callee.find_sym(name)
            assert isinstance(sym, Symbol)
            if sym.is_self():
                continue
            if sym.is_typevar():
                typevars.add(sym)
            if not caller.has_sym(name):
                if sym.scope is callee:
                    if sym.typ.has_scope() and sym.typ.scope_name.startswith(callee.name):
                        typ = sym.typ.clone(scope_name=f"{caller.name}.{sym.name}", explicit=True)
                    else:
                        typ = sym.typ.clone()
                    caller.add_sym(name, sym.tags, typ)
                else:
                    caller.import_sym(sym)

    def _replace_type_expr_scope(self, callee: CalleeScope, caller: CallerScope):
        if not callee.is_ctor():
            return
        orig_callee = env.origin_registry.scope_origin_of(callee)
        assert isinstance(orig_callee, Scope)
        parent = orig_callee.parent
        assert isinstance(parent, Scope)
        value_map = {orig_callee.name: caller.name}
        for field in parent.symbols.values():
            for expr_t in typehelper.find_expr(field.typ):
                if expr_t.scope is orig_callee:
                    d = dataclasses.asdict(field.typ)
                    dd = {}
                    if typehelper.replace_type_dict(d, dd, "scope_name", value_map):
                        field.typ = field.typ.__class__.from_dict(dd)

    def _rename_type_expr_var(self, callee: CalleeScope, old_name: str, new_name: str):
        if not callee.is_ctor():
            return
        orig_callee = env.origin_registry.scope_origin_of(callee)
        assert isinstance(orig_callee, Scope)
        parent = orig_callee.parent
        assert isinstance(parent, Scope)
        renamer = _SymbolRenamer({old_name: new_name})
        for field in parent.symbols.values():
            for expr_t in typehelper.find_expr(field.typ):
                assert isinstance(expr_t, ExprType)
                expr_stm = expr_t.expr
                assert isinstance(expr_stm, Expr)
                new_exp = renamer.visit(expr_stm.exp)
                if new_exp is not expr_stm.exp:
                    new_expr_stm = expr_stm.model_copy(update={'exp': new_exp})
                    new_expr_t = dataclasses.replace(expr_t, expr=new_expr_stm)
                    field.typ = replace_exprtype_in_typ(field.typ, expr_t, new_expr_t)

    def _merge_closure(self, callee: CalleeScope, caller: CallerScope):
        closures = callee.closures()
        if not closures:
            return
        assert callee.is_enclosure()
        for clos in closures:
            env.remove_scope(clos)
            clos.parent = caller
            env.append_scope(clos)
            self._new_scopes.append(clos)
            caller.append_child(clos)
        caller.add_tag("enclosure")

    def _clone_callee(self, caller: CallerScope, callee: CalleeScope) -> CalleeScope:
        callee_clone: CalleeScope = cast(
            CalleeScope, callee.clone("", f"#{self.inline_counts}", parent=callee.parent, recursive=True)
        )
        return callee_clone

    def _remove_closure_if_needed(self, caller: CallerScope):
        assert caller.is_enclosure()
        caller_name_exps = LocalVariableCollector().process(caller)
        has_reference = False
        for clos in caller.closures():
            for name_exp in caller_name_exps:
                if name_exp.name == clos.base_name:
                    has_reference = True
                    break
            else:
                Scope.destroy(clos)
                caller.del_sym(clos.base_name)
        if not has_reference:
            caller.del_tag("enclosure")
            for sym in caller.symbols.values():
                if sym.is_free():
                    sym.del_tag("free")
            assert not caller.closures()

    def _inlining(self, caller: CallerScope, callee: CalleeScope, call_irs: list[CallStmPair]) -> bool:
        for call, call_stm in call_irs:
            can_continue = True
            self.inline_counts += 1
            callee_clone: CalleeScope = self._clone_callee(caller, callee)
            self._import_nonlocal_symbols(callee_clone, caller)
            self._rename(callee_clone, caller)

            replace_map = {}
            replace_arg_map = self._make_replace_args_map(callee_clone, call)
            replace_map |= replace_arg_map
            if callee.is_method():
                replace_self_map = self._make_replace_self_obj_map(callee_clone, call, call_stm, caller)
                replace_map |= replace_self_map
            # Resolve free variable constants from the enclosing scope
            if callee.is_closure():
                replace_freevar_map = self._resolve_free_var_constants(callee_clone)
                replace_map |= replace_freevar_map
            IrReplacer(replace_map).process(callee_clone, callee_clone.entry_block)
            for c in callee_clone.collect_scope():
                IrReplacer(replace_map).process(c, c.entry_block)

            if callee.is_returnable():
                new_call_stm = self._replace_result_exp(call_stm, call, callee_clone, caller)
                if new_call_stm is not None:
                    call_stm = new_call_stm
            if callee_clone.children:
                self._merge_closure(callee_clone, caller)
                can_continue = False
            self._replace_type_expr_scope(callee_clone, caller)
            self._merge_symbols(callee_clone, caller)
            # When inlining a closure/lambda into a worker, mark the caller as
            # a closure so that ConstantOpt's _propagate_to_closure can find it
            # via closures(). Skip if the caller is the enclosure (direct parent
            # of the closure) since that's a normal inline, not a cross-scope
            # propagation case.
            if callee.is_closure() and not caller.is_closure() and not caller.is_enclosure():
                caller.add_tag("closure")
            block_map, _ = callee_clone.clone_blocks(caller)
            callee_entry_blk = block_map[callee_clone.entry_block]
            callee_exit_blk = block_map[callee_clone.exit_block]
            assert len(callee_exit_blk.succs) <= 1
            self._merge_blocks(call_stm, callee.is_ctor(), callee_entry_blk, callee_exit_blk, caller)

            if isinstance(call_stm, Move) and callee.is_ctor():
                assert call_stm.src == call
                builtin_new = SysCall(func=Temp("$new"), args=(("typ", call.func.clone(ctx=Ctx.LOAD)),), kwargs={})
                new_call_stm = call_stm.subst(call_stm.src, builtin_new)
                if new_call_stm is not call_stm:
                    caller.find_block(call_stm.block).replace_stm(call_stm, new_call_stm)
            elif isinstance(call_stm, Expr):
                caller.find_block(call_stm.block).stms.remove(call_stm)

            if caller.is_enclosure():
                self._remove_closure_if_needed(caller)

            if callee_clone.name in env.scopes:
                Scope.destroy(callee_clone)
                callee_clone.parent.del_sym(callee_clone.base_name)
            if not can_continue:
                return False
        return True

    def _replace_result_exp(self, call_stm: IrStm, call: IrCallable, callee: CalleeScope, caller: CallerScope):
        syms = callee.find_syms_by_tags({"return"})
        assert len(syms) == 1
        result_sym = syms.pop()
        result_sym.del_tag("return")
        result = Temp(result_sym.name)
        match call_stm:
            case Move() as move:
                assert move.src == call
                new_stm = move.model_copy(update={"src": result})
            case Expr() as expr:
                assert expr.exp == call
                new_stm = expr.model_copy(update={"exp": result})
            case _:
                return
        blk = caller.find_block(call_stm.block)
        return blk.replace_stm(call_stm, new_stm)

    def _merge_blocks(
        self, call_stm: IrStm, is_ctor: bool, callee_entry_blk: Block, callee_exit_blk: Block, caller: "Scope | None" = None
    ):
        caller_scope = caller if caller else self.scope  # type: ignore[attr-defined]
        early_call_blk = caller_scope.find_block(call_stm.block)
        late_call_blk = Block(caller_scope)
        late_call_blk.succs = early_call_blk.succs
        late_call_blk.succs_loop = early_call_blk.succs_loop
        late_call_blk.synth_params = early_call_blk.synth_params.copy()
        for succ in late_call_blk.succs:
            succ.replace_pred(early_call_blk, late_call_blk)
            succ.replace_pred_loop(early_call_blk, late_call_blk)

        idx = early_call_blk.stms.index(call_stm)
        if is_ctor:
            idx += 1
        late_call_blk.stms = early_call_blk.stms[idx:]
        # In-place block update required: calls list holds stm references
        for s in late_call_blk.stms:
            object.__setattr__(s, "block", late_call_blk.bid)
        early_call_blk.stms = early_call_blk.stms[:idx]
        early_call_blk.append_stm(Jump(callee_entry_blk.bid))
        early_call_blk.succs = [callee_entry_blk]
        early_call_blk.succs_loop = []
        callee_entry_blk.preds = [early_call_blk]

        if callee_exit_blk.stms and isinstance(callee_exit_blk.stms[-1], Ret):
            callee_exit_blk.stms.pop()
        callee_exit_blk.append_stm(Jump(late_call_blk.bid))
        callee_exit_blk.succs = [late_call_blk]
        late_call_blk.preds = [callee_exit_blk]

        if caller_scope.exit_block is early_call_blk:
            caller_scope.exit_block = late_call_blk

        self._merge_synth_params(early_call_blk.synth_params, late_call_blk, callee_entry_blk, callee_exit_blk)

    def _merge_synth_params(self, synth_params, late_call_blk, callee_entry_blk, callee_exit_blk):
        assert synth_params
        for blk in callee_entry_blk.traverse():
            if blk is late_call_blk:
                continue
            merge_synth_params(blk.synth_params, synth_params)

    def _reduce_useless_move(self, scope: Scope):
        for block in scope.traverse_blocks():
            removes = []
            for stm in block.stms:
                if (
                    isinstance(stm, Move)
                    and isinstance(stm.dst, Temp)
                    and isinstance(stm.src, Temp)
                    and stm.dst.name == stm.src.name
                ):
                    removes.append(stm)
            for rm in removes:
                block.stms.remove(rm)


# ============================================================
# FlattenModule
# ============================================================
class FlattenModule(IrVisitor):
    """Flatten module method calls using new IR.

    Converts sub-module worker append calls:
        self.sub.append_worker(self.sub.worker, ...) => self.append_worker(self.worker, ...)
    """

    def process(self, scope):  # type: ignore[override]
        self._new_scopes = []
        if scope.parent and scope.parent.is_module():
            super().process(scope)
        return self._new_scopes

    def _update_current_stm(self, new_call):
        """Update current_stm's Call/SysCall field with the new model_copy'd call."""
        from ..ir import Move, Expr

        stm = self.current_stm
        if isinstance(stm, Move):
            new_stm = stm.model_copy(update={"src": new_call})
        elif isinstance(stm, Expr):
            new_stm = stm.model_copy(update={"exp": new_call})
        else:
            return
        blk = self.scope.find_block(stm.block)
        blk.replace_stm(stm, new_stm)
        self.current_stm = new_stm

    def visit_Call(self, ir):
        callee_scope = self._get_callee_scope(ir)
        if (
            callee_scope.is_method()
            and callee_scope.parent.is_module()
            and callee_scope.base_name == "append_worker"
            and ir.func.head_name() == env.self_name
            and len(ir.func.qualified_name) > 2
        ):
            _, arg = ir.args[0]
            arg_t = irexp_type(arg, self.scope)
            worker_scope = arg_t.scope
            if worker_scope.is_method():
                new_worker, new_arg = self._make_new_worker(ir, arg)
                self._new_scopes.append(new_worker)
                new_worker.parent.register_worker(new_worker)
                assert self.scope.parent.is_module()
                new_func = Attr(name="append_worker", exp=Temp(name="self"), attr="append_worker", ctx=Ctx.CALL)
                new_args = list(ir.args)
                new_args[0] = ("", new_arg)
                ir = ir.model_copy(update={"func": new_func, "name": new_func.name, "args": tuple(new_args)})
                self._update_current_stm(ir)
            else:
                assert self.scope.parent.is_module()
                new_func = Attr(name="append_worker", exp=Temp(name="self"), attr="append_worker", ctx=Ctx.CALL)
                new_args = list(ir.args)
                new_args[0] = (None, arg)
                ir = ir.model_copy(update={"func": new_func, "name": new_func.name, "args": tuple(new_args)})
                self._update_current_stm(ir)
        elif (
            callee_scope.is_method()
            and callee_scope.parent.is_port()
            and callee_scope.base_name == "assign"
            and ir.func.head_name() == env.self_name
            and len(ir.func.qualified_name) > 3
        ):
            _, arg = ir.args[0]
            sym_t = irexp_type(arg, self.scope)
            if not sym_t.is_function():
                return
            sym_scope = sym_t.scope
            if not sym_scope.is_closure() and not sym_scope.is_assigned():
                return
            if sym_scope.is_method() and sym_scope.parent is not self.scope.parent:
                new_method, new_arg = self._make_new_assigned_method(arg, sym_scope)
                self._new_scopes.append(new_method)
                new_args = list(ir.args)
                new_args[0] = ("", new_arg)
                ir = ir.model_copy(update={'args': tuple(new_args)})
                self._update_current_stm(ir)
        else:
            # Visit args
            for _, arg in ir.args:
                self.visit(arg)

    def _get_callee_scope(self, ir):
        qsyms = qualified_symbols(ir.func, self.scope)
        symbol = qsyms[-1]
        assert isinstance(symbol, Symbol)
        func_t = symbol.typ
        assert func_t.has_scope()
        return func_t.scope

    def _make_new_worker(self, call_ir, arg):
        parent_module = self.scope.parent
        qsym = qualified_symbols(arg, self.scope)
        arg_sym = qsym[-1]
        assert isinstance(arg_sym, Symbol)
        arg_t = arg_sym.typ
        worker_scope = arg_t.scope
        assert isinstance(arg, Attr)
        inst_name = cast(IrNameExp, arg.exp).name
        new_worker = worker_scope.clone(inst_name, "", parent=parent_module)
        if new_worker.is_inlinelib():
            new_worker.del_tag("inlinelib")
        worker_self = new_worker.find_sym("self")
        worker_self.typ = worker_self.typ.clone(scope=parent_module)
        in_self = new_worker.param_symbols(with_self=True)[0]
        in_self.typ = in_self.typ.clone(scope=parent_module)

        replace_map = {}
        replace_map[worker_self] = Attr(exp=Temp("self"), attr=inst_name)
        IrReplacer(replace_map).process(new_worker, new_worker.entry_block)
        return new_worker, Attr(
            name=new_worker.base_name, exp=Temp(name="self"), attr=new_worker.base_name, ctx=Ctx.LOAD
        )

    def _make_new_assigned_method(self, arg, assigned_scope):
        module_scope = self.scope.parent
        inst_name = arg.exp.name
        new_method = assigned_scope.clone(inst_name, "", parent=module_scope)
        if new_method.is_inlinelib():
            new_method.del_tag("inlinelib")
        self_sym = new_method.find_sym("self")
        self_sym.typ = self_sym.typ.clone(scope=module_scope)

        in_self = new_method.param_symbols(with_self=True)[0]
        in_self.typ = in_self.typ.clone(scope=module_scope)

        replace_map = {}
        replace_map[self_sym] = Attr(exp=Temp("self"), attr=inst_name)
        IrReplacer(replace_map).process(new_method, new_method.entry_block)

        return new_method, Attr(
            name=new_method.base_name, exp=Temp(name="self"), attr=new_method.base_name, ctx=Ctx.LOAD
        )
