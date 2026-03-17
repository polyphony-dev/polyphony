"""VarReplacer using new IR (ir.py).

Replaces all uses of a variable with a given expression.
"""
from __future__ import annotations
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
from ..symbol import Symbol
from ..analysis.usedef import UseDefDetector
from logging import getLogger
logger = getLogger(__name__)
if TYPE_CHECKING:
    from ..scope import Scope
    from ..analysis.usedef import UseDefTable


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
        uses = list(usedef.get_stms_using(dst_qsym))
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
        new_args = [(name, self.visit(arg)) for name, arg in ir.args]
        func_changed = new_func is not ir.func
        args_changed = any(na is not oa for (_, na), (_, oa) in zip(new_args, ir.args))
        if not func_changed and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_SysCall(self, ir):
        new_func = self.visit(ir.func)
        new_args = [(name, self.visit(arg)) for name, arg in ir.args]
        func_changed = new_func is not ir.func
        args_changed = any(na is not oa for (_, na), (_, oa) in zip(new_args, ir.args))
        if not func_changed and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_New(self, ir):
        new_func = self.visit(ir.func)
        new_args = [(name, self.visit(arg)) for name, arg in ir.args]
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
        return ir.model_copy(update={'repeat': new_repeat, 'items': new_items})

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
                    self.replaced = False
                    object.__setattr__(expr, 'exp', self.visit(expr.exp))
                    self.scope = old_scope

    def visit_with_context(self, scope, irstm):
        # ExprType.expr is now new IR Expr — visit directly
        old_scope = self.scope
        self.scope = scope
        self.visit(irstm)
        self.scope = old_scope

    def visit_Expr(self, ir):
        self.replaced = False
        object.__setattr__(ir, 'exp', self.visit(ir.exp))
        if self.replaced:
            self.replaces.append(ir)

    def visit_CJump(self, ir):
        self.replaced = False
        object.__setattr__(ir, 'exp', self.visit(ir.exp))
        if self.replaced:
            self.replaces.append(ir)

    def visit_MCJump(self, ir):
        self.replaced = False
        object.__setattr__(ir, 'conds', [self.visit(cond) for cond in ir.conds])
        if self.replaced:
            self.replaces.append(ir)

    def visit_Jump(self, ir):
        pass

    def visit_Ret(self, ir):
        pass

    def visit_Move(self, ir):
        self.replaced = False
        object.__setattr__(ir, 'src', self.visit(ir.src))
        if self.enable_dst_replacing:
            object.__setattr__(ir, 'dst', self.visit(ir.dst))
        if self.replaced:
            self.replaces.append(ir)

    def visit_CExpr(self, ir):
        self.replaced = False
        object.__setattr__(ir, 'cond', self.visit(ir.cond))
        self.visit_Expr(ir)

    def visit_CMove(self, ir):
        self.replaced = False
        object.__setattr__(ir, 'cond', self.visit(ir.cond))
        self.visit_Move(ir)

    def visit_Phi(self, ir):
        self.replaced = False
        if self.enable_dst_replacing:
            object.__setattr__(ir, 'var', self.visit(ir.var))
        object.__setattr__(ir, 'args', [self.visit(arg) for arg in ir.args])
        object.__setattr__(ir, 'ps', [self.visit(p) for p in ir.ps])
        if self.replaced:
            self.replaces.append(ir)

    def visit_UPhi(self, ir):
        self.visit_Phi(ir)

    def visit_LPhi(self, ir):
        self.visit_Phi(ir)

    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ir)
        return None
