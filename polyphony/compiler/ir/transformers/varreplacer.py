from __future__ import annotations
from typing import TYPE_CHECKING
from ..ir import *
from ..irhelper import qualified_symbols, irexp_type
from ..types import typehelper
from logging import getLogger
logger = getLogger(__name__)
if TYPE_CHECKING:
    from ..scope import Scope
    from ..analysis.usedef import UseDefTable

class VarReplacer(object):
    @classmethod
    def replace_uses(cls, scope: Scope, dst: IRVariable, src: IRExp):
        assert dst.is_a(IRVariable)
        assert src.is_a(IRExp)
        assert scope.usedef
        usedef = scope.usedef
        logger.debug('replace ' + str(dst) + ' => ' + str(src))
        replacer = VarReplacer(scope, dst, src, usedef)
        dst_qsym = qualified_symbols(dst, scope)
        uses = list(usedef.get_stms_using(dst_qsym))
        for use in uses:
            scope.usedef.remove_var_use(scope, dst, use)
            replacer.visit(use)

        for blk in scope.traverse_blocks():
            if blk.path_exp and blk.path_exp.is_a(IRVariable):
                if blk.path_exp.name == dst.name:
                    blk.path_exp = src
        return replacer.replaces

    def __init__(self, scope: Scope, dst: IRVariable, src: IRExp, usedef: UseDefTable, enable_dst=False):
        super().__init__()
        self.scope = scope
        self.replaces = []
        self.replace_dst = dst
        self.replace_src = src
        self.usedef = usedef
        self.replaced = False
        self.enable_dst_replacing = enable_dst

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_CONDOP(self, ir):
        ir.cond = self.visit(ir.cond)
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_CALL(self, ir):
        ir.func = self.visit(ir.func)
        ir.args = [(name, self.visit(arg)) for name, arg in ir.args]
        return ir

    def visit_SYSCALL(self, ir):
        ir.func = self.visit(ir.func)
        ir.args = [(name, self.visit(arg)) for name, arg in ir.args]
        return ir

    def visit_NEW(self, ir):
        ir.func = self.visit(ir.func)
        ir.args = [(name, self.visit(arg)) for name, arg in ir.args]
        return ir

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        ir.mem = self.visit(ir.mem)
        ir.offset = self.visit(ir.offset)
        return ir

    def visit_MSTORE(self, ir):
        ir.mem = self.visit(ir.mem)
        ir.offset = self.visit(ir.offset)
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_ARRAY(self, ir):
        ir.repeat = self.visit(ir.repeat)
        items = []
        for item in ir.items:
            items.append(self.visit(item))
        ir.items = items
        return ir

    def visit_TEMP(self, ir):
        if ir.name == self.replace_dst.name:
            self.replaced = True
            ir = self.replace_src.clone()
        if ir.is_a(IRVariable):
            typ = irexp_type(ir, self.scope)
            for expr_t in typehelper.find_expr(typ):
                expr = expr_t.expr
                assert expr.is_a(EXPR)
                self.visit_with_context(expr_t.scope, expr)
        return ir

    def visit_ATTR(self, ir):
        if ir.qualified_name == self.replace_dst.qualified_name:
            self.replaced = True
            ir = self.replace_src.clone()
        else:
            ir.exp = self.visit(ir.exp)
        if ir.is_a(IRVariable):
            sym = qualified_symbols(ir, self.scope)[-1]
            assert isinstance(sym, Symbol)
            for expr_t in typehelper.find_expr(sym.typ):
                expr = expr_t.expr
                assert expr.is_a(EXPR)
                self.visit_with_context(expr_t.scope, expr)
        return ir

    def visit_with_context(self, scope: Scope, irstm: IRStm):
        old_scope = self.scope
        self.scope = scope
        self.visit(irstm)
        self.scope = old_scope

    def visit_EXPR(self, ir):
        self.replaced = False
        ir.exp = self.visit(ir.exp)
        if self.replaced:
            self.replaces.append(ir)

    def visit_CJUMP(self, ir):
        self.replaced = False
        ir.exp = self.visit(ir.exp)
        if self.replaced:
            self.replaces.append(ir)

    def visit_MCJUMP(self, ir):
        self.replaced = False
        ir.conds = [self.visit(cond) for cond in ir.conds]
        if self.replaced:
            self.replaces.append(ir)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        pass

    def visit_MOVE(self, ir):
        self.replaced = False
        ir.src = self.visit(ir.src)
        if self.enable_dst_replacing:
            ir.dst = self.visit(ir.dst)
        if self.replaced:
            self.replaces.append(ir)

    def visit_CEXPR(self, ir):
        self.replaced = False
        ir.cond = self.visit(ir.cond)
        self.visit_EXPR(ir)

    def visit_CMOVE(self, ir):
        self.replaced = False
        ir.cond = self.visit(ir.cond)
        self.visit_MOVE(ir)

    def visit_PHI(self, ir):
        self.replaced = False
        if self.enable_dst_replacing:
            ir.var = self.visit(ir.var)
        ir.args = [self.visit(arg) for arg in ir.args]
        ir.ps = [self.visit(p) for p in ir.ps]
        if self.replaced:
            self.replaces.append(ir)

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

    def visit_LPHI(self, ir):
        self.visit_PHI(ir)

    def visit(self, ir:IR) -> IR:
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ir)
        else:
            return None
