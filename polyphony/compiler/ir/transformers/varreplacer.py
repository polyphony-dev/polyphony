"""VarReplacer using new IR (ir.py).

Replaces all uses of a variable with a given expression.
"""
from __future__ import annotations
from dataclasses import replace as dataclasses_replace
from typing import TYPE_CHECKING
from ..ir import (
    Ir, IrExp, IrStm, IrVariable, IrNameExp,
    Temp, Attr, Const, UnOp, BinOp, RelOp, CondOp,
    Call, SysCall, New, MRef, MStore, Array,
    Move, CMove, Expr, CExpr, CJump, MCJump, Jump, Ret,
    Phi, UPhi, LPhi,
)
from ..irhelper import qualified_symbols, irexp_type
from ..types import typehelper
from ..types.exprtype import ExprType
from ..symbol import Symbol
from ..analysis.usedef import UseDefDetector
from logging import getLogger
logger = getLogger(__name__)
if TYPE_CHECKING:
    from ..scope import Scope
    from ..analysis.usedef import UseDefTable


def replace_exprtype_in_typ(typ, old_expr_t: ExprType, new_expr_t: ExprType):
    """Replace old_expr_t with new_expr_t in the type tree, returning updated type."""
    if typ is old_expr_t:
        return new_expr_t
    if typ.is_list():
        new_element = replace_exprtype_in_typ(typ.element, old_expr_t, new_expr_t)
        new_length = typ.length
        if isinstance(typ.length, ExprType):
            new_length = replace_exprtype_in_typ(typ.length, old_expr_t, new_expr_t)
        if new_element is typ.element and new_length is typ.length:
            return typ
        return typ.clone(element=new_element, length=new_length)
    if typ.is_tuple():
        new_element = replace_exprtype_in_typ(typ.element, old_expr_t, new_expr_t)
        if new_element is typ.element:
            return typ
        return typ.clone(element=new_element)
    return typ


class VarReplacer(object):
    @classmethod
    def replace_uses(cls, scope, dst, src, usedef=None):
        assert isinstance(dst, IrVariable)
        assert isinstance(src, IrExp)
        if usedef is None:
            usedef = UseDefDetector().process(scope)
        logger.debug('replace ' + str(dst) + ' => ' + str(src))
        replacer = VarReplacer(scope, dst, src, usedef)
        dst_qsym = qualified_symbols(dst, scope)
        def _stm_key(stm):
            blk = scope.find_block(stm.block)
            if blk is None:
                return (0, 0)
            idx = next((i for i, s in enumerate(blk.stms) if s is stm), -1)
            return (blk.order, idx)
        uses = sorted(usedef.get_stms_using(dst_qsym), key=_stm_key)
        for use in uses:
            replacer.visit(use)

        for blk in scope.traverse_blocks():
            if blk.path_exp and isinstance(blk.path_exp, IrVariable):
                if blk.path_exp.name == dst.name:
                    blk.path_exp = src

        # Replace in ExprType.expr across all scopes (mirrors old VarReplacer)
        replacer._replace_in_expr_types(scope)
        return replacer.replaces

    def __init__(self, scope, dst, src, usedef, enable_dst=False):
        self.scope = scope
        self.replaces = []
        self.replace_dst = dst
        self.replace_src = src
        self.usedef = usedef
        self.replaced = False
        self.enable_dst_replacing = enable_dst

    def _replace_stm_in_block(self, old_stm: IrStm, new_stm: IrStm) -> IrStm:
        """Replace old_stm with new_stm in its block and update usedef.

        Returns new_stm unchanged if old_stm has no block (orphan, e.g. ExprType.expr).
        """
        if not old_stm.block:
            return new_stm
        blk = self.scope.find_block(old_stm.block)
        new_stm = blk.replace_stm(old_stm, new_stm)
        if self.usedef:
            self.usedef.replace_stm(old_stm, new_stm)
        return new_stm

    def _replace_stm(self, old_ir: IrStm, new_ir: IrStm) -> IrStm:
        """Replace and record stm; skip block/usedef update if old_ir is an orphan (no block)."""
        new_ir = self._replace_stm_in_block(old_ir, new_ir)
        if old_ir.block:
            self.replaces.append(new_ir)
        return new_ir

    def visit_UnOp(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is ir.exp:
            return ir
        return ir.model_copy(update={'exp': new_exp})

    def visit_BinOp(self, ir):
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_left is ir.left and new_right is ir.right:
            return ir
        return ir.model_copy(update={'left': new_left, 'right': new_right})

    def visit_RelOp(self, ir):
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_left is ir.left and new_right is ir.right:
            return ir
        return ir.model_copy(update={'left': new_left, 'right': new_right})

    def visit_CondOp(self, ir):
        new_cond = self.visit(ir.cond)
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_cond is ir.cond and new_left is ir.left and new_right is ir.right:
            return ir
        return ir.model_copy(update={'cond': new_cond, 'left': new_left, 'right': new_right})

    def visit_Call(self, ir):
        new_func = self.visit(ir.func)
        new_args = tuple((name, self.visit(arg)) for name, arg in ir.args)
        func_changed = new_func is not ir.func
        args_changed = any(na is not oa for (_, na), (_, oa) in zip(new_args, ir.args))
        if not func_changed and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_SysCall(self, ir):
        new_func = self.visit(ir.func)
        new_args = tuple((name, self.visit(arg)) for name, arg in ir.args)
        func_changed = new_func is not ir.func
        args_changed = any(na is not oa for (_, na), (_, oa) in zip(new_args, ir.args))
        if not func_changed and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_New(self, ir):
        new_func = self.visit(ir.func)
        new_args = tuple((name, self.visit(arg)) for name, arg in ir.args)
        func_changed = new_func is not ir.func
        args_changed = any(na is not oa for (_, na), (_, oa) in zip(new_args, ir.args))
        if not func_changed and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_Const(self, ir):
        return ir

    def visit_MRef(self, ir):
        new_mem = self.visit(ir.mem)
        new_offset = self.visit(ir.offset)
        if new_mem is ir.mem and new_offset is ir.offset:
            return ir
        return ir.model_copy(update={'mem': new_mem, 'offset': new_offset})

    def visit_MStore(self, ir):
        new_mem = self.visit(ir.mem)
        new_offset = self.visit(ir.offset)
        new_exp = self.visit(ir.exp)
        if new_mem is ir.mem and new_offset is ir.offset and new_exp is ir.exp:
            return ir
        return ir.model_copy(update={'mem': new_mem, 'offset': new_offset, 'exp': new_exp})

    def visit_Array(self, ir):
        new_repeat = self.visit(ir.repeat)
        new_items = [self.visit(item) for item in ir.items]
        repeat_changed = new_repeat is not ir.repeat
        items_changed = any(ni is not oi for ni, oi in zip(new_items, ir.items))
        if not repeat_changed and not items_changed:
            return ir
        return ir.model_copy(update={'repeat': new_repeat, 'items': tuple(new_items)})

    def visit_Temp(self, ir):
        if ir.name == self.replace_dst.name:
            self.replaced = True
            ir = self.replace_src.model_copy(deep=True)
        else:
            # Only visit type expressions for non-replaced variables,
            # since replaced values come from a different scope
            if isinstance(ir, IrVariable):
                typ = irexp_type(ir, self.scope)
                for expr_t in typehelper.find_expr(typ):
                    expr = expr_t.expr
                    self.visit_with_context(expr_t.scope, expr)
        return ir

    def visit_Attr(self, ir):
        if ir.qualified_name == self.replace_dst.qualified_name:
            self.replaced = True
            ir = self.replace_src.model_copy(deep=True)
        else:
            new_exp = self.visit(ir.exp)
            if new_exp is not ir.exp:
                ir = ir.model_copy(update={'exp': new_exp})
        if isinstance(ir, IrVariable):
            sym = qualified_symbols(ir, self.scope)[-1]
            assert isinstance(sym, Symbol)
            for expr_t in typehelper.find_expr(sym.typ):
                expr = expr_t.expr
                self.visit_with_context(expr_t.scope, expr)
        return ir

    def _replace_in_expr_types(self, scope):
        """Replace dst variable in ExprType.expr across all scopes."""
        from ...common.env import env
        for s in env.scopes.values():
            for sym in s.symbols.values():
                for expr_t in typehelper.find_expr(sym.typ):
                    if expr_t.scope is not scope:
                        continue
                    expr = expr_t.expr
                    old_scope = self.scope
                    self.scope = expr_t.scope
                    new_exp = self.visit(expr.exp)
                    self.scope = old_scope
                    if new_exp is expr.exp:
                        continue
                    new_expr = expr.model_copy(update={'exp': new_exp})
                    new_expr_t = dataclasses_replace(expr_t, expr=new_expr)
                    sym.typ = replace_exprtype_in_typ(sym.typ, expr_t, new_expr_t)
                    if expr.block:
                        blk = scope.find_block(expr.block)
                        blk.replace_stm(expr, new_expr)

    def visit_with_context(self, scope, irstm):
        # ExprType.expr is now new IR Expr — visit directly
        old_scope = self.scope
        self.scope = scope
        new_irstm = self.visit(irstm)
        self.scope = old_scope
        return new_irstm

    def visit_Expr(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is ir.exp:
            return ir
        return self._replace_stm(ir, ir.model_copy(update={'exp': new_exp}))

    def visit_CJump(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is ir.exp:
            return ir
        return self._replace_stm(ir, ir.model_copy(update={'exp': new_exp}))

    def visit_MCJump(self, ir):
        new_conds = tuple(self.visit(cond) for cond in ir.conds)
        if all(nc is oc for nc, oc in zip(new_conds, ir.conds)):
            return ir
        return self._replace_stm(ir, ir.model_copy(update={'conds': new_conds}))

    def visit_Jump(self, ir):
        pass

    def visit_Ret(self, ir):
        pass

    def visit_Move(self, ir):
        new_src = self.visit(ir.src)
        new_dst = self.visit(ir.dst) if self.enable_dst_replacing else ir.dst
        if new_src is ir.src and new_dst is ir.dst:
            return ir
        updates = {}
        if new_src is not ir.src:
            updates['src'] = new_src
        if new_dst is not ir.dst:
            updates['dst'] = new_dst
        return self._replace_stm(ir, ir.model_copy(update=updates))

    def visit_CExpr(self, ir):
        new_cond = self.visit(ir.cond)
        new_exp = self.visit(ir.exp)
        if new_cond is ir.cond and new_exp is ir.exp:
            return ir
        updates = {}
        if new_cond is not ir.cond:
            updates['cond'] = new_cond
        if new_exp is not ir.exp:
            updates['exp'] = new_exp
        return self._replace_stm(ir, ir.model_copy(update=updates))

    def visit_CMove(self, ir):
        new_cond = self.visit(ir.cond)
        new_src = self.visit(ir.src)
        new_dst = self.visit(ir.dst) if self.enable_dst_replacing else ir.dst
        if new_cond is ir.cond and new_src is ir.src and new_dst is ir.dst:
            return ir
        updates = {}
        if new_cond is not ir.cond:
            updates['cond'] = new_cond
        if new_src is not ir.src:
            updates['src'] = new_src
        if new_dst is not ir.dst:
            updates['dst'] = new_dst
        return self._replace_stm(ir, ir.model_copy(update=updates))

    def visit_Phi(self, ir):
        new_var = self.visit(ir.var) if self.enable_dst_replacing else ir.var
        new_args = tuple(self.visit(arg) for arg in ir.args)
        new_ps = tuple(self.visit(p) for p in ir.ps)
        var_changed = new_var is not ir.var
        args_changed = any(na is not oa for na, oa in zip(new_args, ir.args))
        ps_changed = any(np_ is not op for np_, op in zip(new_ps, ir.ps))
        if not var_changed and not args_changed and not ps_changed:
            return ir
        updates = {}
        if var_changed:
            updates['var'] = new_var
        if args_changed:
            updates['args'] = new_args
        if ps_changed:
            updates['ps'] = new_ps
        return self._replace_stm(ir, ir.model_copy(update=updates))

    def visit_UPhi(self, ir):
        return self.visit_Phi(ir)

    def visit_LPhi(self, ir):
        return self.visit_Phi(ir)

    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ir)
        return None
