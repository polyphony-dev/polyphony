class IRVisitor:
    def __init__(self):
        self.done_blocks = []

    def process(self, scope):
        self.scope = scope
        assert len(scope.blocks[0].preds) == 0
        self._process_Block(scope.blocks[0])
        self._process_scope_done(scope)

    def _process_scope_done(self, scope):
        pass

    def _process_Block(self, block):
        if block not in self.done_blocks:
            self.block = block
            for stm in block.stms:
                self.current_stm = stm
                self.visit(stm)

            self.done_blocks.append(block)
            for succ in block.succs:
                self._process_Block(succ)

    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir)

    def visit_UNOP(self, ir):
        self.visit(ir.exp)

    def visit_BINOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_RELOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        for arg in ir.args:
            self.visit(arg)

    def visit_SYSCALL(self, ir):
        for arg in ir.args:
            self.visit(arg)

    def visit_CTOR(self, ir):
        for arg in ir.args:
            self.visit(arg)

    def visit_CONST(self, ir):
        pass

    def visit_TEMP(self, ir):
        pass

    def visit_ATTR(self, ir):
        self.visit(ir.exp)

    def visit_MREF(self, ir):
        self.visit(ir.mem)
        self.visit(ir.offset)

    def visit_MSTORE(self, ir):
        self.visit(ir.mem)
        self.visit(ir.offset)
        self.visit(ir.exp)

    def visit_ARRAY(self, ir):
        for item in ir.items:
            self.visit(item)

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        self.visit(ir.exp)

    def visit_MOVE(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)

    def visit_PHI(self, ir):
        pass


class IRTransformer(IRVisitor):
    def __init__(self):
        self.done_blocks = []

    def _process_Block(self, block):
        if block not in self.done_blocks:
            self.block = block
            self.new_stms = []
            for stm in block.stms:
                self.current_stm = stm
                self.visit(stm)
            block.stms = self.new_stms
            #set the pointer to the block to each stm
            for stm in block.stms:
                stm.block = block

            self.done_blocks.append(block)
            for succ in block.succs:
                self._process_Block(succ)

    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir)


