from .ir import CONST, TEMP, BINOP
from logging import getLogger
logger = getLogger(__name__)

class VarReplacer:
    @classmethod
    def replace_uses(cls, dst, src, usedef):
        assert dst.is_a(TEMP)
        logger.debug('replace ' + str(dst) + ' => ' + str(src))
        replacer = VarReplacer(dst, src, usedef)
        uses = list(usedef.get_use_stms_by_sym(dst.sym))
        for use in uses: 
            replacer.current_stm = use
            replacer.visit(use)
        return replacer.replaces


    def __init__(self, dst, src, usedef):
        super().__init__()
        self.replaces = []
        self.replace_dst = dst
        self.replace_src = src
        self.usedef = usedef
        self.replaced = False

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

    def visit_CALL(self, ir):
        ir.args = [self.visit(arg) for arg in ir.args]
        return ir

    def visit_SYSCALL(self, ir):
        return self.visit_CALL(ir)

    def visit_CTOR(self, ir):
        return self.visit_CALL(ir)

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
        items = []
        for item in ir.items:
            items.append(self.visit(item))
        ir.items = items
        return ir

    def visit_TEMP(self, ir):
        if ir.sym is self.replace_dst.sym:
            self.replaced = True
            rep = self.replace_src.clone()
            self.usedef.remove_var_use(ir, self.current_stm)
            if rep.is_a(TEMP):
                self.usedef.add_var_use(rep, self.current_stm)
            return rep
        return ir

    def visit_ATTR(self, ir):
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
        if self.replaced:
            self.replaces.append(ir)

    def visit_PHI(self, ir):
        self.replaced = False
        ir.args = [(self.visit(arg), blk) for arg, blk in ir.args]
        if self.replaced:
            self.replaces.append(ir)

    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir)
            
