"""Visitor and Transformer for IR (ir.py).

IrVisitor / IrTransformer: traversal of IR via block.stms (PascalCase visit methods).
Dispatch is based on class name: visit(ir) calls visit_<ClassName>(ir).
"""
from .ir import (
    Ir, IrExp, IrStm, Jump, CJump, MCJump,
)


class IrVisitor(object):
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
        if isinstance(ir, IrStm):
            self.current_stm = ir
        if visitor:
            return visitor(ir)
        return None

    # --- IrExp ---

    def visit_UnOp(self, ir):
        self.visit(ir.exp)

    def visit_BinOp(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_RelOp(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_CondOp(self, ir):
        self.visit(ir.cond)
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_PolyOp(self, ir):
        for v in ir.values:
            self.visit(v)

    def _visit_args(self, args, kwargs):
        for _, arg in args:
            self.visit(arg)
        for kwarg in kwargs.values():
            self.visit(kwarg)

    def visit_Call(self, ir):
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_SysCall(self, ir):
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_New(self, ir):
        self.visit(ir.func)
        self._visit_args(ir.args, ir.kwargs)

    def visit_Const(self, ir):
        pass

    def visit_Temp(self, ir):
        pass

    def visit_Attr(self, ir):
        self.visit(ir.exp)

    def visit_MRef(self, ir):
        self.visit(ir.mem)
        self.visit(ir.offset)

    def visit_MStore(self, ir):
        self.visit(ir.mem)
        self.visit(ir.offset)
        self.visit(ir.exp)

    def visit_Array(self, ir):
        if ir.repeat is not None:
            self.visit(ir.repeat)
        for item in ir.items:
            self.visit(item)

    # --- IrStm ---

    def visit_Expr(self, ir):
        self.visit(ir.exp)

    def visit_CExpr(self, ir):
        self.visit(ir.cond)
        self.visit_Expr(ir)

    def visit_Move(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)

    def visit_CMove(self, ir):
        self.visit(ir.cond)
        self.visit_Move(ir)

    def visit_CJump(self, ir):
        self.visit(ir.exp)

    def visit_MCJump(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_Jump(self, ir):
        pass

    def visit_Ret(self, ir):
        self.visit(ir.exp)

    def visit_Phi(self, ir):
        self.visit(ir.var)
        for arg in ir.args:
            if arg:
                self.visit(arg)
        for p in ir.ps:
            if p:
                self.visit(p)

    def visit_UPhi(self, ir):
        self.visit_Phi(ir)

    def visit_LPhi(self, ir):
        self.visit_Phi(ir)

    def visit_MStm(self, ir):
        for stm in ir.stms:
            self.visit(stm)


class IrTransformer(IrVisitor):
    """Functional IR transformer (IrExp is frozen).

    Each visit_* method for expressions returns a new node (or the original if unchanged).
    Each visit_* method for statements mutates in-place (IrStm is still mutable) and
    appends to self.new_stms.

    Subclasses override specific visit_* methods to implement transformations.
    """
    def __init__(self):
        pass

    def _process_block(self, block):
        self.new_stms = []
        for stm in block.stms:
            self.visit(stm)
        block.stms = self.new_stms
        self.new_stms = []
        if block.path_exp:
            block.path_exp = self.visit(block.path_exp)
        if block.stms and isinstance(block.stms[-1], (Jump, CJump, MCJump)):
            block.stms = block.stms[:-1] + self.new_stms + [block.stms[-1]]
        else:
            block.stms.extend(self.new_stms)
        for stm in block.stms:
            object.__setattr__(stm, 'block', block.bid)

    # --- IrExp (return transformed node, functional style) ---

    def visit_UnOp(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is ir.exp:
            return ir
        return ir.model_copy(update={'exp': new_exp})

    def visit_BinOp(self, ir):
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_left is ir.left and new_right is ir.right:
            return ir
        return ir.model_copy(update={'left': new_left, 'right': new_right})

    def visit_RelOp(self, ir):
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_left is ir.left and new_right is ir.right:
            return ir
        return ir.model_copy(update={'left': new_left, 'right': new_right})

    def visit_CondOp(self, ir):
        new_cond = self.visit(ir.cond)
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_cond is ir.cond and new_left is ir.left and new_right is ir.right:
            return ir
        return ir.model_copy(update={'cond': new_cond, 'left': new_left, 'right': new_right})

    def visit_PolyOp(self, ir):
        new_values = [self.visit(v) for v in ir.values]
        if all(nv is ov for nv, ov in zip(new_values, ir.values)):
            return ir
        return ir.model_copy(update={'values': new_values})

    def _visit_args(self, args):
        new_args = [(name, self.visit(arg)) for name, arg in args]
        changed = any(na is not oa for (_, na), (_, oa) in zip(new_args, args))
        return new_args, changed

    def visit_Call(self, ir):
        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        if new_func is ir.func and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_SysCall(self, ir):
        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        if new_func is ir.func and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_New(self, ir):
        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        if new_func is ir.func and not args_changed:
            return ir
        return ir.model_copy(update={'func': new_func, 'args': new_args})

    def visit_Const(self, ir):
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_Attr(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is ir.exp:
            return ir
        return ir.model_copy(update={'exp': new_exp})

    def visit_MRef(self, ir):
        new_mem = self.visit(ir.mem)
        new_offset = self.visit(ir.offset)
        if new_mem is ir.mem and new_offset is ir.offset:
            return ir
        return ir.model_copy(update={'mem': new_mem, 'offset': new_offset})

    def visit_MStore(self, ir):
        new_mem = self.visit(ir.mem)
        new_offset = self.visit(ir.offset)
        new_exp = self.visit(ir.exp)
        if new_mem is ir.mem and new_offset is ir.offset and new_exp is ir.exp:
            return ir
        return ir.model_copy(update={'mem': new_mem, 'offset': new_offset, 'exp': new_exp})

    def visit_Array(self, ir):
        new_repeat = self.visit(ir.repeat) if ir.repeat is not None else ir.repeat
        new_items = [self.visit(item) for item in ir.items]
        repeat_changed = new_repeat is not ir.repeat
        items_changed = any(ni is not oi for ni, oi in zip(new_items, ir.items))
        if not repeat_changed and not items_changed:
            return ir
        return ir.model_copy(update={'repeat': new_repeat, 'items': new_items})

    # --- IrStm (append to new_stms, IrStm is still mutable) ---

    def visit_Expr(self, ir):
        object.__setattr__(ir, 'exp', self.visit(ir.exp))
        self.new_stms.append(ir)

    def visit_CExpr(self, ir):
        object.__setattr__(ir, 'cond', self.visit(ir.cond))
        self.visit_Expr(ir)

    def visit_Move(self, ir):
        object.__setattr__(ir, 'src', self.visit(ir.src))
        object.__setattr__(ir, 'dst', self.visit(ir.dst))
        self.new_stms.append(ir)

    def visit_CMove(self, ir):
        object.__setattr__(ir, 'cond', self.visit(ir.cond))
        self.visit_Move(ir)

    def visit_CJump(self, ir):
        object.__setattr__(ir, 'exp', self.visit(ir.exp))
        self.new_stms.append(ir)

    def visit_MCJump(self, ir):
        for i, cond in enumerate(ir.conds):
            ir.conds[i] = self.visit(cond)
        self.new_stms.append(ir)

    def visit_Jump(self, ir):
        self.new_stms.append(ir)

    def visit_Ret(self, ir):
        object.__setattr__(ir, 'exp', self.visit(ir.exp))
        self.new_stms.append(ir)

    def visit_Phi(self, ir):
        object.__setattr__(ir, 'var', self.visit(ir.var))
        for i, arg in enumerate(ir.args):
            if arg:
                ir.args[i] = self.visit(arg)
        if ir.ps:
            for i, p in enumerate(ir.ps):
                if p:
                    ir.ps[i] = self.visit(p)
        self.new_stms.append(ir)

    def visit_UPhi(self, ir):
        self.visit_Phi(ir)

    def visit_LPhi(self, ir):
        self.visit_Phi(ir)

    def visit_MStm(self, ir):
        for stm in ir.stms:
            method = 'visit_' + stm.__class__.__name__
            visitor = getattr(self, method, None)
            if visitor:
                visitor(stm)
            self.new_stms.pop()
        self.new_stms.append(ir)

