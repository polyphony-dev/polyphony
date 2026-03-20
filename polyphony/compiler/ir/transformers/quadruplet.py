"""QuadrupleMakers using new IR (ir.py).

EarlyQuadrupleMaker makes quadruples:
  tmp <= tmp
  tmp <= tmp (op) tmp
  tmp <= function(*tmp)
  tmp <= constant
  tmp <= mem[offset]
  mem[offset] <= tmp
  if condition then bb1 else bb2
  goto bb
"""
from ..ir import (
    Temp, Attr, Const, UnOp, BinOp, RelOp, CondOp,
    Call, SysCall, New, MRef, MStore, Array,
    Move, Expr, CJump, MCJump,
    Ctx,
)
from ..irvisitor import IrTransformer
from ...common.common import fail
from ...common.errors import Errors


class EarlyQuadrupleMaker(IrTransformer):
    def __init__(self):
        super().__init__()
        self.suppress_converting = False

    def _new_temp_move(self, ir, tmpsym):
        mv = Move(
            dst=Temp(name=tmpsym.name, ctx=Ctx.STORE),
            src=ir,
            loc=self.current_stm.loc,
        )
        self.new_stms.append(mv)
        return Temp(name=tmpsym.name)

    def visit_UnOp(self, ir):
        new_exp = self.visit(ir.exp)
        if not isinstance(new_exp, (Temp, Attr, Const, MRef)):
            fail(self.current_stm, Errors.UNSUPPORTED_EXPR)
        if new_exp is not ir.exp:
            return ir.model_copy(update={'exp': new_exp})
        return ir

    def visit_BinOp(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False

        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_left is not ir.left or new_right is not ir.right:
            ir = ir.model_copy(update={'left': new_left, 'right': new_right})

        assert isinstance(ir.left, (Temp, Attr, Const, UnOp, MRef, Array))
        assert isinstance(ir.right, (Temp, Attr, Const, UnOp, MRef))

        if isinstance(ir.left, Array):
            if ir.op == 'Mult':
                array = ir.left
                if isinstance(array.repeat, Const) and array.repeat.value == 1:
                    return array.model_copy(update={'repeat': ir.right})
                else:
                    return array.model_copy(update={'repeat': BinOp(op='Mult', left=array.repeat, right=ir.right)})
            else:
                fail(self.current_stm, Errors.UNSUPPORTED_EXPR)

        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_RelOp(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_left is not ir.left or new_right is not ir.right:
            ir = ir.model_copy(update={'left': new_left, 'right': new_right})
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_condition_sym())

    def visit_CondOp(self, ir):
        new_cond = self.visit(ir.cond)
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_cond is not ir.cond or new_left is not ir.left or new_right is not ir.right:
            ir = ir.model_copy(update={'cond': new_cond, 'left': new_left, 'right': new_right})
        return self._new_temp_move(ir, self.scope.add_temp())

    def _visit_args(self, args):  # type: ignore[override]
        new_args = []
        changed = False
        for name, arg in args:
            new_arg = self.visit(arg)
            assert isinstance(new_arg, (Temp, Attr, Const, UnOp, Array))
            if isinstance(new_arg, Array):
                new_arg = self._new_temp_move(new_arg, self.scope.add_temp())
            if new_arg is not arg:
                changed = True
            new_args.append((name, new_arg))
        return tuple(new_args), changed

    def visit_Call(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        if new_func is not ir.func or args_changed:
            ir = ir.model_copy(update={'func': new_func, 'args': new_args})
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_SysCall(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        if new_func is not ir.func or args_changed:
            ir = ir.model_copy(update={'func': new_func, 'args': new_args})
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_New(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        if new_func is not ir.func or args_changed:
            ir = ir.model_copy(update={'func': new_func, 'args': new_args})
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_Const(self, ir):
        return ir

    def visit_MRef(self, ir):
        suppress = self.suppress_converting
        if isinstance(ir.mem, MRef):
            self.suppress_converting = True
        else:
            self.suppress_converting = False
        new_mem = self.visit(ir.mem)
        new_offset = self.visit(ir.offset)
        if new_mem is not ir.mem or new_offset is not ir.offset:
            ir = ir.model_copy(update={'mem': new_mem, 'offset': new_offset})
        if not isinstance(ir.offset, (Temp, Attr, Const, UnOp)):
            fail(self.current_stm, Errors.UNSUPPORTED_EXPR)
        if not suppress and ir.ctx & Ctx.LOAD:
            return self._new_temp_move(ir, self.scope.add_temp())
        return ir

    def visit_MStore(self, ir):
        return ir

    def visit_Array(self, ir):
        new_items = [self.visit(item) for item in ir.items]
        items_changed = any(ni is not oi for ni, oi in zip(new_items, ir.items))
        if items_changed:
            return ir.model_copy(update={'items': tuple(new_items)})
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_Attr(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            return ir.model_copy(update={'exp': new_exp})
        return ir

    def visit_Expr(self, ir):
        if isinstance(ir.exp, (Call, SysCall, MStore)):
            self.suppress_converting = True
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            ir = ir.model_copy(update={'exp': new_exp})
        self.new_stms.append(ir)

    def visit_CJump(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            ir = ir.model_copy(update={'exp': new_exp})
        sym = self.scope.find_sym(ir.exp.name) if isinstance(ir.exp, Temp) else None
        assert (sym is not None and sym.is_condition()) or isinstance(ir.exp, Const)
        self.new_stms.append(ir)

    def visit_MCJump(self, ir):
        new_conds = []
        changed = False
        for cond in ir.conds:
            new_cond = self.visit(cond)
            assert isinstance(new_cond, (Temp, Const))
            if new_cond is not cond:
                changed = True
            new_conds.append(new_cond)
        if changed:
            ir = ir.model_copy(update={'conds': tuple(new_conds)})
        self.new_stms.append(ir)

    def visit_Move(self, ir):
        if isinstance(ir.src, (BinOp, RelOp, Call, SysCall, New, MRef)):
            self.suppress_converting = True
        new_src = self.visit(ir.src)
        new_dst = self.visit(ir.dst)
        if new_src is not ir.src or new_dst is not ir.dst:
            ir = ir.model_copy(update={'src': new_src, 'dst': new_dst})
        assert isinstance(ir.src, (Temp, Attr, Const, UnOp,
                                   BinOp, RelOp, MRef, Call,
                                   New, SysCall, Array))
        assert isinstance(ir.dst, (Temp, Attr, MRef, Array))

        if isinstance(ir.dst, MRef):
            mref = ir.dst
            ms = MStore(mem=mref.mem, offset=mref.offset, exp=self.visit(ir.src))
            expr = Expr(exp=ms, loc=ir.loc)
            ir = expr
        self.new_stms.append(ir)


class LateQuadrupleMaker(IrTransformer):
    def visit_Attr(self, ir):
        from ..irhelper import qualified_symbols
        from ..symbol import Symbol
        qsyms = qualified_symbols(ir, self.scope)
        attr_sym = qsyms[-1]
        receiver = qsyms[-2]
        assert isinstance(attr_sym, Symbol)
        assert isinstance(receiver, Symbol)
        attr_t = attr_sym.typ
        receiver_t = receiver.typ
        if (receiver_t.is_class() or receiver_t.is_namespace()) and attr_t.is_scalar():
            return ir
        new_exp = self.visit(ir.exp)
        if new_exp is ir.exp:
            return ir
        return ir.model_copy(update={'exp': new_exp})
