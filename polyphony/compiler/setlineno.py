from collections import defaultdict
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

    def visit_CONDOP(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.cond)
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_CALL(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.func)
        self.visit_args(ir.args, ir.kwargs)

    def visit_SYSCALL(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit_args(ir.args, ir.kwargs)

    def visit_NEW(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit_args(ir.args, ir.kwargs)

    def visit_CONST(self, ir):
        ir.lineno = self.current_stm.lineno

    def visit_TEMP(self, ir):
        ir.lineno = self.current_stm.lineno

    def visit_ATTR(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.exp)

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
        self.visit(ir.repeat)
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

    def process(self, scope):
        self.stms = defaultdict(list)
        super().process(scope)
        logger.debug('-' * 30)
        logger.debug(scope.name)
        logger.debug('-' * 30)
        for lineno in sorted(self.stms.keys()):
            src_line = get_src_text(scope, lineno)
            src_line = src_line.replace('\n', '')
            logger.debug('{}:{}'.format(lineno, src_line))
            spc_nums = len(src_line) - len(src_line.lstrip())
            indent = ' ' * spc_nums
            for stm in self.stms[lineno]:
                logger.debug(indent + str(stm))

    def _process_block(self, block):
        for stm in block.stms:
            self.stms[stm.lineno].append(stm)
