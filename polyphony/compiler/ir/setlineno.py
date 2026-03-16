from collections import defaultdict
from .ir_visitor import IrVisitor
from ..common.common import get_src_text
import logging
logger = logging.getLogger()


class LineNumberSetter(IrVisitor):
    def __init__(self):
        super().__init__()

    def visit_UnOp(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.exp)

    def visit_BinOp(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_RelOp(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_CondOp(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.cond)
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_Call(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_SysCall(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_New(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_Const(self, ir):
        ir.lineno = self.current_stm.lineno

    def visit_Temp(self, ir):
        ir.lineno = self.current_stm.lineno

    def visit_Attr(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.exp)

    def visit_MRef(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.mem)
        self.visit(ir.offset)

    def visit_MStore(self, ir):
        ir.lineno = self.current_stm.lineno
        self.visit(ir.mem)
        self.visit(ir.offset)
        self.visit(ir.exp)

    def visit_Array(self, ir):
        ir.lineno = self.current_stm.lineno
        if ir.repeat is not None:
            self.visit(ir.repeat)
        for item in ir.items:
            self.visit(item)

    def visit_Expr(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.exp)

    def visit_CJump(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.exp)

    def visit_MCJump(self, ir):
        assert ir.lineno >= 0
        for cond in ir.conds:
            self.visit(cond)

    def visit_Jump(self, ir):
        assert ir.lineno >= 0

    def visit_Ret(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.exp)

    def visit_Move(self, ir):
        assert ir.lineno >= 0
        self.visit(ir.src)
        self.visit(ir.dst)

    def visit_Phi(self, ir):
        pass


class SourceDump(IrVisitor):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        self.stms = defaultdict(list)
        super().process(scope)
        logger.debug('-' * 30)
        logger.debug(scope.name)
        logger.debug('-' * 30)
        for loc in sorted(self.stms.keys()):
            src_line = get_src_text(loc.filename, loc.lineno)
            src_line = src_line.replace('\n', '')
            logger.debug('{}:{}'.format(loc.lineno, src_line))
            spc_nums = len(src_line) - len(src_line.lstrip())
            indent = ' ' * spc_nums
            for stm in self.stms[loc]:
                logger.debug(indent + str(stm))

    def _process_block(self, block):
        for stm in block.stms:
            self.stms[stm.loc].append(stm)
