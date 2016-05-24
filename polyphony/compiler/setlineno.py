from .irvisitor import IRVisitor
from .common import get_src_text
import logging
logger = logging.getLogger()

class LineNumberSetter(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.exp)

    def visit_BINOP(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_RELOP(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_CALL(self, ir):
        ir.lineno = self.current_stm.lineno
        for arg in ir.args:
            self.visit(arg)

    def visit_SYSCALL(self, ir):
        ir.lineno = self.current_stm.lineno
        for arg in ir.args:
            self.visit(arg)

    def visit_CTOR(self, ir):
        ir.lineno = self.current_stm.lineno
        for arg in ir.args:
            self.visit(arg)

    def visit_CONST(self, ir):
        ir.lineno = self.current_stm.lineno

    def visit_TEMP(self, ir):
        ir.lineno = self.current_stm.lineno

    def visit_ATTR(self, ir):
        ir.lineno = self.current_stm.lineno

    def visit_MREF(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.mem)
        self.visit(ir.offset)

    def visit_MSTORE(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.mem)
        self.visit(ir.offset)
        self.visit(ir.exp)

    def visit_ARRAY(self, ir):
        ir.lineno = self.current_stm.lineno
        for item in ir.items:
            self.visit(item)

    def visit_EXPR(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        assert ir.lineno >= 0
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        assert ir.lineno >= 0

    def visit_RET(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.exp)

    def visit_MOVE(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.src)
        self.visit(ir.dst)

    def visit_PHI(self, ir):
        pass


class SourceDump(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        pass

    def visit_BINOP(self, ir):
        pass

    def visit_RELOP(self, ir):
        pass

    def visit_CALL(self, ir):
        pass

    def visit_SYSCALL(self, ir):
        pass
    
    def visit_CONST(self, ir):
        pass

    def visit_TEMP(self, ir):
        pass

    def visit_MREF(self, ir):
        pass

    def visit_MSTORE(self, ir):
        pass

    def visit_ARRAY(self, ir):
        pass

    def visit_EXPR(self, ir):
        logger.debug(str(ir))
        logger.debug(get_src_text(ir.lineno))

    def visit_CJUMP(self, ir):
        logger.debug(str(ir))
        logger.debug(get_src_text(ir.lineno))

    def visit_MCJUMP(self, ir):
        logger.debug(str(ir))
        logger.debug(get_src_text(ir.lineno))

    def visit_JUMP(self, ir):
        logger.debug(str(ir))
        logger.debug(get_src_text(ir.lineno))

    def visit_RET(self, ir):
        logger.debug(str(ir))
        logger.debug(get_src_text(ir.lineno))

    def visit_MOVE(self, ir):
        logger.debug(str(ir))
        logger.debug(get_src_text(ir.lineno))

    def visit_PHI(self, ir):
        pass

    
