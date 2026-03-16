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
from ..ir_visitor import IrTransformer
from ...common.common import fail
from ...common.errors import Errors


class NewEarlyQuadrupleMaker(IrTransformer):
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
        ir.exp = self.visit(ir.exp)
        if not isinstance(ir.exp, (Temp, Attr, Const, MRef)):
            fail(self.current_stm, Errors.UNSUPPORTED_EXPR)
        return ir

    def visit_BinOp(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)

        assert isinstance(ir.left, (Temp, Attr, Const, UnOp, MRef, Array))
        assert isinstance(ir.right, (Temp, Attr, Const, UnOp, MRef))

        if isinstance(ir.left, Array):
            if ir.op == 'Mult':
                array = ir.left
                if isinstance(array.repeat, Const) and array.repeat.value == 1:
                    array.repeat = ir.right
                else:
                    array.repeat = BinOp(op='Mult', left=array.repeat, right=ir.right)
                return array
            else:
                fail(self.current_stm, Errors.UNSUPPORTED_EXPR)

        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_RelOp(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_condition_sym())

    def visit_CondOp(self, ir):
        ir.cond = self.visit(ir.cond)
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return self._new_temp_move(ir, self.scope.add_temp())

    def _visit_args(self, args):
        for i, (name, arg) in enumerate(args):
            arg = self.visit(arg)
            assert isinstance(arg, (Temp, Attr, Const, UnOp, Array))
            if isinstance(arg, Array):
                arg = self._new_temp_move(arg, self.scope.add_temp())
            args[i] = (name, arg)

    def visit_Call(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        ir.func = self.visit(ir.func)
        self._visit_args(ir.args)
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_SysCall(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        ir.func = self.visit(ir.func)
        self._visit_args(ir.args)
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_New(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        ir.func = self.visit(ir.func)
        self._visit_args(ir.args)
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
        ir.mem = self.visit(ir.mem)
        ir.offset = self.visit(ir.offset)
        if not isinstance(ir.offset, (Temp, Attr, Const, UnOp)):
            fail(self.current_stm, Errors.UNSUPPORTED_EXPR)
        if not suppress and ir.ctx & Ctx.LOAD:
            return self._new_temp_move(ir, self.scope.add_temp())
        return ir

    def visit_MStore(self, ir):
        return ir

    def visit_Array(self, ir):
        for i in range(len(ir.items)):
            ir.items[i] = self.visit(ir.items[i])
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_Attr(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_Expr(self, ir):
        if isinstance(ir.exp, (Call, SysCall, MStore)):
            self.suppress_converting = True
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJump(self, ir):
        ir.exp = self.visit(ir.exp)
        assert (isinstance(ir.exp, Temp) and self.scope.find_sym(ir.exp.name).is_condition()) or isinstance(ir.exp, Const)
        self.new_stms.append(ir)

    def visit_MCJump(self, ir):
        for i in range(len(ir.conds)):
            ir.conds[i] = self.visit(ir.conds[i])
            assert isinstance(ir.conds[i], (Temp, Const))
        self.new_stms.append(ir)

    def visit_Move(self, ir):
        if isinstance(ir.src, (BinOp, RelOp, Call, SysCall, New, MRef)):
            self.suppress_converting = True
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
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


class NewLateQuadrupleMaker(IrTransformer):
    def visit_Attr(self, ir):
        from ..ir_helper import qualified_symbols
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
        ir.exp = self.visit(ir.exp)
        return ir
