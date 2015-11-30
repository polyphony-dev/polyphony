from ir import BINOP, RELOP, CALL, CONST, MREF, ARRAY, TEMP, EXPR, CJUMP, JUMP, MOVE
from common import logger
from irvisitor import IRTransformer

class CallTransformer(IRTransformer):
    def __init__(self):
        super().__init__()

    def visit_BINOP(self, ir):
        return ir

    def visit_RELOP(self, ir):
        return ir

    def visit_CALL(self, ir):
        return ir

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        return ir

    def visit_ARRAY(self, ir):
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_EXPR(self, ir):
        self.new_stms.append(ir)

    def visit_PARAM(self, ir):
        #self.new_stms.append(ir)
        pass

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_JUMP(self, ir):
        self.new_stms.append(ir)

    def visit_MOVE(self, ir):
        if isinstance(ir.src, CALL):
            #self.new_stms.append(EXPR(ir.src))
            self.new_stms.append(MOVE(ir.src.func, ir.src))
            self.new_stms.append(CALL_RET(ir.dst, TEMP(ir.src.func.sym, 'Load')))
        else:
            self.new_stms.append(ir)

