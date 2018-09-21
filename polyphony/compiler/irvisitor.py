from .ir import IRStm


class IRVisitor(object):
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
            self.visit(stm)
        if block.path_exp:
            self.visit(block.path_exp)

    def visit(self, ir):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if ir.is_a(IRStm):
            self.current_stm = ir
        if visitor:
            return visitor(ir)
        else:
            return None

    def visit_UNOP(self, ir):
        self.visit(ir.exp)

    def visit_BINOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_RELOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_args(self, args, kwargs):
        for _, arg in args:
            self.visit(arg)
        for kwarg in kwargs.values():
            self.visit(kwarg)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        self.visit_args(ir.args, ir.kwargs)

    def visit_SYSCALL(self, ir):
        self.visit_args(ir.args, ir.kwargs)

    def visit_NEW(self, ir):
        self.visit_args(ir.args, ir.kwargs)

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

    def visit_CEXPR(self, ir):
        self.visit(ir.cond)
        self.visit_EXPR(ir)

    def visit_CMOVE(self, ir):
        self.visit(ir.cond)
        self.visit_MOVE(ir)

    def visit_PHI(self, ir):
        self.visit(ir.var)
        for arg in ir.args:
            if arg:
                self.visit(arg)
        for p in ir.ps:
            if p:
                self.visit(p)

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

    def visit_LPHI(self, ir):
        self.visit_PHI(ir)


class IRTransformer(IRVisitor):
    def __init__(self):
        pass

    def _process_block(self, block):
        self.new_stms = []
        for stm in block.stms:
            self.visit(stm)
        block.stms = self.new_stms
        #set the pointer to the block to each stm
        for stm in block.stms:
            stm.block = block
        if block.path_exp:
            block.path_exp = self.visit(block.path_exp)

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

    def visit_args(self, args):
        for i, (name, arg) in enumerate(args):
            args[i] = (name, self.visit(arg))

    def visit_CALL(self, ir):
        ir.func = self.visit(ir.func)
        self.visit_args(ir.args)
        return ir

    def visit_SYSCALL(self, ir):
        self.visit_args(ir.args)
        return ir

    def visit_NEW(self, ir):
        self.visit_args(ir.args)
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

    def visit_CEXPR(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_EXPR(ir)

    def visit_CMOVE(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_MOVE(ir)

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

    def visit_LPHI(self, ir):
        self.visit_PHI(ir)
