class IRVisitor:
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        assert len(scope.entry_block.preds) == 0

        for blk in self.scope.traverse_blocks():
            self._process_block(blk)
        self._process_scope_done(scope)

    def _process_scope_done(self, scope):
        pass

    def _process_block(self, block):
        for stm in block.stms:
            self.current_stm = stm
            self.visit(stm)

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

    def visit_NEW(self, ir):
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
        self.visit(ir.repeat)
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
        self.visit(ir.var)
        for arg in ir.args:
            self.visit(arg)
        if ir.ps:
            for p in ir.ps:
                if p : self.visit(p)

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)


class IRTransformer(IRVisitor):
    def __init__(self):
        pass

    def _process_block(self, block):
        self.new_stms = []
        for stm in block.stms:
            self.current_stm = stm
            self.visit(stm)
        block.stms = self.new_stms
        #set the pointer to the block to each stm
        for stm in block.stms:
            stm.block = block


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
        ir.func = self.visit(ir.func)
        for i, arg in enumerate(ir.args):
            ir.args[i] = self.visit(arg)
        return ir

    def visit_SYSCALL(self, ir):
        for i, arg in enumerate(ir.args):
            ir.args[i] = self.visit(arg)
        return ir

    def visit_NEW(self, ir):
        for i, arg in enumerate(ir.args):
            ir.args[i] = self.visit(arg)
        return ir

    def visit_CONST(self, ir):
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_ATTR(self, ir):
        ir.exp = self.visit(ir.exp)
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
        for i, item in enumerate(ir.items):
            ir.items[i] = self.visit(item)
        return ir

    def visit_EXPR(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MCJUMP(self, ir):
        for i, cond in enumerate(ir.conds):
            ir.conds[i] = self.visit(cond)
        self.new_stms.append(ir)

    def visit_JUMP(self, ir):
        self.new_stms.append(ir)

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        self.new_stms.append(ir)

    def visit_PHI(self, ir):
        ir.var = self.visit(ir.var)
        for i, arg in enumerate(ir.args):
            ir.args[i] = self.visit(arg)
        if ir.ps:
            for i, p in enumerate(ir.ps):
                ir.ps[i] = self.visit(p)
        self.new_stms.append(ir)

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)
