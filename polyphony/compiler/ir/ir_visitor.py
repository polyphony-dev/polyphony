"""Visitor and Transformer for IR (ir.py).

IrVisitor / IrTransformer: traversal of IR via block.stms (PascalCase visit methods).
IRVisitor / IRTransformer: traversal of IR via block.stms (UPPERCASE visit methods),
    with backward-compat fallback from PascalCase class names to UPPERCASE visit methods.

Dispatch is based on class name: visit(ir) calls visit_<ClassName>(ir).
"""
from .ir import (
    Ir, IrExp, IrStm, Jump, CJump, MCJump,
)

# Mapping from new IR class names to old visit method names (backward compat)
_NEW_TO_OLD_VISIT = {
    'Const': 'visit_CONST', 'Temp': 'visit_TEMP', 'Attr': 'visit_ATTR',
    'UnOp': 'visit_UNOP', 'BinOp': 'visit_BINOP', 'RelOp': 'visit_RELOP',
    'CondOp': 'visit_CONDOP', 'PolyOp': 'visit_POLYOP',
    'Call': 'visit_CALL', 'SysCall': 'visit_SYSCALL', 'New': 'visit_NEW',
    'MRef': 'visit_MREF', 'MStore': 'visit_MSTORE', 'Array': 'visit_ARRAY',
    'Expr': 'visit_EXPR', 'CExpr': 'visit_CEXPR',
    'Move': 'visit_MOVE', 'CMove': 'visit_CMOVE',
    'Jump': 'visit_JUMP', 'CJump': 'visit_CJUMP', 'MCJump': 'visit_MCJUMP',
    'Ret': 'visit_RET',
    'Phi': 'visit_PHI', 'UPhi': 'visit_UPHI', 'LPhi': 'visit_LPHI',
    'MStm': 'visit_MSTM',
}


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
            method = 'visit_' + stm.__class__.__name__
            visitor = getattr(self, method, None)
            if visitor:
                visitor(stm)


class IrTransformer(IrVisitor):
    """In-place IR transformer for Phase 1 (frozen=False).

    Each visit_* method for expressions returns the (possibly modified) node.
    Each visit_* method for statements appends to self.new_stms.

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
        # NOTE: block.path_exp is old IR and must not be visited by new IrTransformer.
        # It will be handled after full migration.
        if block.stms and isinstance(block.stms[-1], (Jump, CJump, MCJump)):
            block.stms = block.stms[:-1] + self.new_stms + [block.stms[-1]]
        else:
            block.stms.extend(self.new_stms)
        for stm in block.stms:
            stm.block = block

    # --- IrExp (return transformed node) ---

    def visit_UnOp(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_BinOp(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_RelOp(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_CondOp(self, ir):
        ir.cond = self.visit(ir.cond)
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_PolyOp(self, ir):
        ir.values = [self.visit(v) for v in ir.values]
        return ir

    def _visit_args(self, args):
        for i, (name, arg) in enumerate(args):
            args[i] = (name, self.visit(arg))

    def visit_Call(self, ir):
        ir.func = self.visit(ir.func)
        self._visit_args(ir.args)
        return ir

    def visit_SysCall(self, ir):
        ir.func = self.visit(ir.func)
        self._visit_args(ir.args)
        return ir

    def visit_New(self, ir):
        ir.func = self.visit(ir.func)
        self._visit_args(ir.args)
        return ir

    def visit_Const(self, ir):
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_Attr(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_MRef(self, ir):
        ir.mem = self.visit(ir.mem)
        ir.offset = self.visit(ir.offset)
        return ir

    def visit_MStore(self, ir):
        ir.mem = self.visit(ir.mem)
        ir.offset = self.visit(ir.offset)
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_Array(self, ir):
        if ir.repeat is not None:
            ir.repeat = self.visit(ir.repeat)
        for i, item in enumerate(ir.items):
            ir.items[i] = self.visit(item)
        return ir

    # --- IrStm (append to new_stms) ---

    def visit_Expr(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CExpr(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_Expr(ir)

    def visit_Move(self, ir):
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        self.new_stms.append(ir)

    def visit_CMove(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_Move(ir)

    def visit_CJump(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MCJump(self, ir):
        for i, cond in enumerate(ir.conds):
            ir.conds[i] = self.visit(cond)
        self.new_stms.append(ir)

    def visit_Jump(self, ir):
        self.new_stms.append(ir)

    def visit_Ret(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_Phi(self, ir):
        ir.var = self.visit(ir.var)
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


# ============================================================
# Old-style visitors operating on block.stms with UPPERCASE methods
# and backward-compat fallback for PascalCase IR class names.
# ============================================================

class IRVisitor(object):
    """Visitor for old IR via block.stms, with PascalCase->UPPERCASE fallback."""
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
        cls_name = ir.__class__.__name__
        method = 'visit_' + cls_name
        visitor = getattr(self, method, None)
        # If no direct match and it's a new IR type, try old visit method name
        if visitor is None and cls_name in _NEW_TO_OLD_VISIT:
            visitor = getattr(self, _NEW_TO_OLD_VISIT[cls_name], None)
        if isinstance(ir, (IrStm,)):
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
        self.visit(ir.func)
        self.visit_args(ir.args, ir.kwargs)

    def visit_NEW(self, ir):
        self.visit(ir.func)
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

    def visit_MSTM(self, ir):
        for stm in ir.stms:
            self.visit(stm)


class IRTransformer(IRVisitor):
    """Transformer for old IR via block.stms, with PascalCase->UPPERCASE fallback."""
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
        ir.func = self.visit(ir.func)
        self.visit_args(ir.args)
        return ir

    def visit_NEW(self, ir):
        ir.func = self.visit(ir.func)
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

    def visit_MSTM(self, ir):
        for stm in ir.stms:
            self.visit(stm)
            self.new_stms.pop()
        self.new_stms.append(ir)
