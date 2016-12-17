from .ir import *
from .common import funclog
from .symbol import Symbol
from .irvisitor import IRTransformer
from .type import Type
from .typecheck import builtin_return_type_table
from .common import error_info

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

class QuadrupleMaker(IRTransformer):
    def __init__(self):
        super().__init__()
        self.suppress_converting = False

    def _new_temp_move(self, ir, prefix):
        tmpsym = self.scope.add_temp(prefix)
        t = TEMP(tmpsym, Ctx.STORE)
        t.lineno = ir.lineno
        mv = MOVE(t, ir)
        mv.lineno = ir.lineno
        assert mv.lineno >= 0
        self.new_stms.append(mv)
        t = TEMP(tmpsym, Ctx.LOAD)
        t.lineno = ir.lineno
        return t

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        assert ir.exp.is_a([TEMP, ATTR, CONST, MREF])
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
                array.repeat = ir.right
                return array
            #if ir.right.is_a(CONST) and ir.op == 'Mult':
            ##    #array times n
             #   array = ir.left
             #   time = ir.right.value
            #    if not array.items:
            #        raise RuntimeError('unsupported expression')
            #    else:
            #        array.items = [item.clone() for item in array.items * time]
            #    return array
            else:
                print(error_info(ir.lineno))
                raise RuntimeError('unsupported expression')

        if suppress:
            return ir
        return self._new_temp_move(ir, Symbol.temp_prefix)

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return self._new_temp_move(ir, Symbol.condition_prefix)

    def _has_return_type(self, ir):
        if ir.is_a(CALL):
            return True# ir.func_scope.return_type != Type.none_t
        elif ir.is_a(SYSCALL):
            return builtin_return_type_table[ir.name] != Type.none_t

    def _visit_args(self, ir):
        for i in range(len(ir.args)):
            ir.args[i] = self.visit(ir.args[i])
            assert ir.args[i].is_a([TEMP, ATTR, CONST, UNOP, ARRAY])
            if ir.args[i].is_a(ARRAY):
                ir.args[i] = self._new_temp_move(ir.args[i], Symbol.temp_prefix)

    def visit_CALL(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.func = self.visit(ir.func)
        self._visit_args(ir)

        if suppress or not self._has_return_type(ir):
            return ir
        return self._new_temp_move(ir, Symbol.temp_prefix)

    def visit_SYSCALL(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        self._visit_args(ir)

        if suppress or not self._has_return_type(ir):
            return ir
        return self._new_temp_move(ir, Symbol.temp_prefix)

    def visit_NEW(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        self._visit_args(ir)

        if suppress:
            return ir
        return self._new_temp_move(ir, Symbol.temp_prefix)

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.offset = self.visit(ir.offset)
        assert ir.offset.is_a([TEMP, ATTR, CONST, UNOP])

        if not suppress and ir.ctx & Ctx.LOAD:
            return self._new_temp_move(ir, Symbol.temp_prefix)
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
        if ir.exp.is_a([CALL, SYSCALL]):
            self.suppress_converting = True
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        assert ir.exp.is_a(TEMP) and ir.exp.sym.is_condition() or ir.exp.is_a(CONST)
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
        if ir.src.is_a([BINOP, CALL, SYSCALL, NEW, MREF]):
            self.suppress_converting = True
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        assert ir.src.is_a([TEMP, ATTR, CONST, UNOP, BINOP, MREF, MSTORE, CALL, NEW, SYSCALL, ARRAY])
        assert ir.dst.is_a([TEMP, ATTR, MREF, ARRAY])

        if ir.dst.is_a(MREF):
            # For the sake of the memory analysis,
            # the assign to a item of a list is formed
            # @mem = mstore(@mem, idx, value)
            # instead of
            # mref(@mem, index) = value
            mref = ir.dst
            mref.mem.ctx = Ctx.LOAD
            ir.src = MSTORE(mref.mem, mref.offset, self.visit(ir.src))
            ir.dst = mref.mem.clone()
            ir.dst.ctx = Ctx.STORE

            ir.src.lineno = ir.lineno
            ir.dst.lineno = ir.lineno
        self.new_stms.append(ir)

