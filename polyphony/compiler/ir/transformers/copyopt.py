"""CopyOpt using new IR (ir.py)."""
from collections import deque
from typing import cast
from ..ir import (
    Ir, IrVariable, IrNameExp, Temp, Attr, Move, CMove, Expr,
    Phi, UPhi, LPhi, Ctx,
)
from ..irvisitor import IrVisitor
from ..irhelper import qualified_symbols
from ..scope import Scope
from ..symbol import Symbol
from ..analysis.usedef import UseDefDetector, UseDefUpdater
from ..analysis.usedef import UseDefItem
from logging import getLogger
logger = getLogger(__name__)


def _replace_in_list(lst, old, new):
    try:
        lst[lst.index(old)] = new
    except ValueError:
        pass


def _replace_in_deque(dq, old, new):
    for i in range(len(dq)):
        if dq[i] is old:
            dq[i] = new
            return


class CopyCollector(IrVisitor):
    def __init__(self, copies):
        self.copies = copies

    def visit_CMove(self, ir):
        return

    def visit_Move(self, ir):
        dst_sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(dst_sym, Symbol)
        dst_t = dst_sym.typ
        if dst_sym.is_return() or dst_sym.is_register() or dst_sym.is_field() or dst_sym.is_free():
            return
        if dst_t.is_function():
            return
        if isinstance(ir.src, Temp):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            src_t = src_sym.typ
            if src_sym.is_param():
                return
            if src_t.clone(explicit=True) != dst_t.clone(explicit=True):
                return
            self.copies.append(ir)
        elif isinstance(ir.src, Attr):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            src_t = src_sym.typ
            if src_t.is_object() and src_t.scope.is_port():
                self.copies.append(ir)


class CopyOpt(object):
    def _new_collector(self, copies):
        return CopyCollector(copies)

    def _find_old_use(self, scope, ir, qname):
        return ir.find_vars(qname)

    def process(self, scope):
        self.scope = scope
        self.usedef = UseDefDetector().process(scope)
        copies = []
        collector = self._new_collector(copies)
        collector.process(scope)
        worklist = deque(copies)
        while worklist:
            cp = worklist.popleft()
            dst_qsym = cast(tuple[Symbol, ...], qualified_symbols(cp.dst, scope))
            defs = list(self.usedef.get_stms_defining(dst_qsym))
            if len(defs) > 1:
                copies.remove(cp)
                continue
            src_qsym = cast(tuple[Symbol, ...], qualified_symbols(cp.src, scope))
            orig = self._find_root_def(src_qsym)
            udupdater = UseDefUpdater(scope, self.usedef)
            replaced = self._replace_copies(scope, udupdater, self.usedef, cp, orig, dst_qsym, copies, worklist)
            if dst_qsym[0].is_free():
                for clos in scope.closures():
                    clos_usedef = UseDefDetector().process(clos)
                    clos_udupdater = UseDefUpdater(clos, clos_usedef)
                    clos_replaced = self._replace_copies(clos, clos_udupdater, clos_usedef, cp, orig, dst_qsym, copies, worklist)
                    if clos_replaced:
                        src_qsym[0].add_tag('free')
        for cp in copies:
            if cp in self.scope.find_block(cp.block).stms:
                if isinstance(cp.dst, Attr) and cast(tuple[Symbol, ...], qualified_symbols(cp.dst, self.scope))[-2].typ.scope.is_module() and scope.is_ctor():
                    continue
                self.scope.find_block(cp.block).stms.remove(cp)

    def _replace_copies(self, scope, udupdater, usedef, copy_stm, orig, target, copies, worklist):
        uses = sorted(list(usedef.get_stms_using(target)), key=lambda u: u.loc[1] if isinstance(u.loc, tuple) and len(u.loc) >= 2 else 0)
        for u in uses:
            qname = tuple(s.name for s in target)
            olds = self._find_old_use(scope, u, qname)
            if not olds:
                continue
            new = orig.model_copy(deep=True) if orig else copy_stm.src.model_copy(deep=True)
            new_u = u.subst(olds[0], new)
            if new_u is not u:
                udupdater.update(u, new_u)
                scope.find_block(u.block).replace_stm(u, new_u)
                _replace_in_list(copies, u, new_u)
                _replace_in_deque(worklist, u, new_u)
                if (isinstance(new_u, Move) and
                        isinstance(new_u.dst, IrVariable) and
                        isinstance(new_u.src, IrVariable) and
                        new_u.src.qualified_name == new_u.dst.qualified_name):
                    scope.find_block(new_u.block).stms.remove(new_u)
                    udupdater.update(new_u, None)
                    continue
                u = new_u
            if isinstance(u, (Phi, UPhi, LPhi)):
                qsyms = [qualified_symbols(arg, self.scope) for arg in u.args
                        if isinstance(arg, IrVariable) and arg.name != u.var.name]
                if qsyms:
                    if len(u.args) == len(qsyms) and all(qsyms[0] == s for s in qsyms):
                        src = u.args[0]
                    elif len(qsyms) == 1 and len([arg for arg in u.args if isinstance(arg, IrVariable)]) > 1:
                        for arg in u.args:
                            if isinstance(arg, IrVariable) and qualified_symbols(arg, self.scope) == qsyms[0]:
                                src = arg
                                break
                        else:
                            assert False
                    else:
                        continue
                    mv = Move(dst=u.var, src=src, block=u.block)
                    u_blk_stms = scope.find_block(u.block).stms; idx = u_blk_stms.index(u)
                    u_blk_stms[idx] = mv
                    udupdater.update(u, mv)
                    if isinstance(mv.src, IrVariable):
                        worklist.append(mv)
                        copies.append(mv)
        return len(uses) > 0

    def _find_root_def(self, qsym, _visited=None):
        if _visited is None:
            _visited = set()
        sym_key = id(qsym[-1])
        if sym_key in _visited:
            return None
        _visited.add(sym_key)
        defs = list(self.usedef.get_stms_defining(qsym))
        if len(defs) != 1:
            return None
        d = defs[0]
        if isinstance(d, Move):
            dst_sym = qualified_symbols(cast(IrNameExp, d.dst), self.scope)[-1]
            assert isinstance(dst_sym, Symbol)
            dst_t = dst_sym.typ
            if isinstance(d.src, (Temp, Attr)):
                src_qsym = qualified_symbols(d.src, self.scope)
                src_sym = src_qsym[-1]
                assert isinstance(src_sym, Symbol)
                if src_sym.is_param():
                    return None
                if src_sym.typ.clone(explicit=True) != dst_t.clone(explicit=True):
                    return None
                orig = self._find_root_def(src_qsym, _visited)
                return orig if orig else d.src
        return None


class ObjCopyCollector(IrVisitor):
    def __init__(self, copies):
        self.copies = copies

    def _is_alias_def(self, mov):
        if not isinstance(mov, Move):
            return False
        if not isinstance(mov.src, IrVariable):
            return False
        if not isinstance(mov.dst, IrVariable):
            return False
        if isinstance(mov.dst, Attr):
            receiver = qualified_symbols(cast(IrNameExp, mov.dst.exp), self.scope)[-1]
            assert isinstance(receiver, Symbol)
            receiver_t = receiver.typ
            if receiver_t.is_object() and receiver_t.scope.is_module():
                return False
        dst_sym = qualified_symbols(mov.dst, self.scope)[-1]
        assert isinstance(dst_sym, Symbol)
        dst_t = dst_sym.typ
        return (dst_t.is_object() or dst_t.is_seq()) and not dst_sym.is_param()

    def visit_CMove(self, ir):
        return

    def visit_Move(self, ir):
        if self._is_alias_def(ir):
            if isinstance(ir.src, IrVariable):
                src_sym = qualified_symbols(ir.src, self.scope)[-1]
                if isinstance(src_sym, Symbol) and not src_sym.is_param():
                        self.copies.append(ir)


class ObjCopyOpt(CopyOpt):
    def _new_collector(self, copies):  # type: ignore[override]
        return ObjCopyCollector(copies)

    def _find_old_use(self, scope, ir, qname):
        vars = []
        def find_vars_rec(node, qname, vars):
            if isinstance(node, Ir):
                if isinstance(node, Attr):
                    if node.qualified_name == qname:
                        vars.append(node)
                    find_vars_rec(node.exp, qname, vars)
                elif isinstance(node, Temp) and len(qname) == 1:
                    sym = scope.find_sym(node.name)
                    if sym and (sym.typ.is_object() or sym.typ.is_seq()):
                        if node.name == qname[0]:
                            vars.append(node)
                else:
                    for field_name in type(node).model_fields:
                        v = getattr(node, field_name, None)
                        find_vars_rec(v, qname, vars)
            elif isinstance(node, (list, tuple)):
                for elm in node:
                    find_vars_rec(elm, qname, vars)
        find_vars_rec(ir, qname, vars)
        return vars
