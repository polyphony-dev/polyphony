﻿from ..ir import *
from ..irvisitor import IRTransformer
from ...common.common import fail
from ...common.errors import Errors

# QuadrupleMaker makes following quadruples.
#
# -  tmp <= tmp
# -  tmp <= tmp (op) tmp
# -  tmp <= function(*tmp)
# -  tmp <= constant
# -  tmp <= mem[offset]
# -  mem[offset] <= tmp
# -  if condition then bb1 else bb2
# -  goto bb


class EarlyQuadrupleMaker(IRTransformer):
    def __init__(self):
        super().__init__()
        self.suppress_converting = False

    def _new_temp_move(self, ir, tmpsym):
        t = TEMP(tmpsym, Ctx.STORE)
        mv = MOVE(t, ir, loc=self.current_stm.loc)
        self.new_stms.append(mv)
        return TEMP(tmpsym, Ctx.LOAD)

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        if not ir.exp.is_a([TEMP, ATTR, CONST, MREF]):
            fail(self.current_stm, Errors.UNSUPPORTED_EXPR)
        return ir

    def visit_BINOP(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)

        assert ir.left.is_a([TEMP, ATTR, CONST, UNOP, MREF, ARRAY])
        assert ir.right.is_a([TEMP, ATTR, CONST, UNOP, MREF])

        if ir.left.is_a(ARRAY):
            if ir.op == 'Mult':
                array = ir.left
                if array.repeat.is_a(CONST) and array.repeat.value == 1:
                    array.repeat = ir.right
                else:
                    array.repeat = BINOP('Mult', array.repeat, ir.right)
                return array
            else:
                fail(self.current_stm, Errors.UNSUPPORTED_EXPR)

        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_RELOP(self, ir):
        suppress = self.suppress_converting
        self.suppress_converting = False
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_condition_sym())

    def visit_CONDOP(self, ir):
        ir.cond = self.visit(ir.cond)
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return self._new_temp_move(ir, self.scope.add_temp())

    def _visit_args(self, ir):
        for i, (name, arg) in enumerate(ir.args):
            arg = self.visit(arg)
            assert arg.is_a([TEMP, ATTR, CONST, UNOP, ARRAY])
            if arg.is_a(ARRAY):
                arg = self._new_temp_move(arg, self.scope.add_temp())
            ir.args[i] = (name, arg)

    def visit_CALL(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.func = self.visit(ir.func)
        self._visit_args(ir)

        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_SYSCALL(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        self._visit_args(ir)

        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_NEW(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        self._visit_args(ir)

        if suppress:
            return ir
        return self._new_temp_move(ir, self.scope.add_temp())

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        if ir.mem.is_a(MREF):
            self.suppress_converting = True
        else:
            self.suppress_converting = False
        ir.mem = self.visit(ir.mem)
        ir.offset = self.visit(ir.offset)
        if not ir.offset.is_a([TEMP, ATTR, CONST, UNOP]):
            fail(self.current_stm, Errors.UNSUPPORTED_EXPR)

        if not suppress and ir.ctx & Ctx.LOAD:
            return self._new_temp_move(ir, self.scope.add_temp())
        return ir

    def visit_MSTORE(self, ir):
        return ir

    def visit_ARRAY(self, ir):
        for i in range(len(ir.items)):
            ir.items[i] = self.visit(ir.items[i])
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_ATTR(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_EXPR(self, ir):
        #We don't convert outermost CALL
        if ir.exp.is_a([CALL, SYSCALL, MSTORE]):
            self.suppress_converting = True
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        assert ir.exp.is_a(TEMP) and ir.exp.symbol.is_condition() or ir.exp.is_a(CONST)
        self.new_stms.append(ir)

    def visit_MCJUMP(self, ir):
        for i in range(len(ir.conds)):
            ir.conds[i] = self.visit(ir.conds[i])
            assert ir.conds[i].is_a([TEMP, CONST])
        self.new_stms.append(ir)

    def visit_JUMP(self, ir):
        self.new_stms.append(ir)

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MOVE(self, ir):
        #We don't convert outermost BINOP or CALL
        if ir.src.is_a([BINOP, RELOP, CALL, SYSCALL, NEW, MREF]):
            self.suppress_converting = True
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        assert ir.src.is_a([TEMP, ATTR, CONST, UNOP,
                            BINOP, RELOP, MREF, CALL,
                            NEW, SYSCALL, ARRAY])
        assert ir.dst.is_a([TEMP, ATTR, MREF, ARRAY])

        if ir.dst.is_a(MREF):
            mref = ir.dst
            # the memory store is not a variable definition, so the context should be LOAD
            # mref.mem.ctx = Ctx.LOAD
            ms = MSTORE(mref.mem, mref.offset, self.visit(ir.src))
            expr = EXPR(ms)
            expr.loc = ir.loc
            ir = expr
        self.new_stms.append(ir)


class LateQuadrupleMaker(IRTransformer):
    def visit_ATTR(self, ir):
        receiver = ir.tail()
        receiver_t = receiver.typ
        attr_t = ir.symbol.typ
        if (receiver_t.is_class() or receiver_t.is_namespace()) and attr_t.is_scalar():
            return ir
        ir.exp = self.visit(ir.exp)

        if ir.exp.is_a(TEMP) and ir.exp.symbol.typ.is_namespace():
            ir_ = TEMP(ir.symbol, ir.ctx)
            ir = ir_
        return ir
