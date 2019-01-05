from .ir import *
from logging import getLogger
logger = getLogger(__name__)


class VarReplacer(object):
    @classmethod
    def replace_uses(cls, dst, src, usedef):
        assert dst.is_a([TEMP, ATTR])
        assert src.is_a([IRExp])
        logger.debug('replace ' + str(dst) + ' => ' + str(src))
        replacer = VarReplacer(dst, src, usedef)
        uses = list(usedef.get_stms_using(dst.qualified_symbol()))
        for use in uses:
            replacer.visit(use)
        return replacer.replaces

    def __init__(self, dst, src, usedef, enable_dst=False):
        super().__init__()
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
        ir.args = [(name, self.visit(arg)) for name, arg in ir.args]
        return ir

    def visit_NEW(self, ir):
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
        if ir.sym is self.replace_dst.symbol():
            self.replaced = True
            rep = self.replace_src.clone()
            rep.lineno = ir.lineno
            return rep
        return ir

    def visit_ATTR(self, ir):
        if ir.qualified_symbol() == self.replace_dst.qualified_symbol():
            self.replaced = True
            rep = self.replace_src.clone()
            rep.lineno = ir.lineno
            return rep
        else:
            ir.exp = self.visit(ir.exp)
        return ir

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

    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ir)
        else:
            return None
