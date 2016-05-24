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
            if ir.right.is_a(CONST) and ir.op == 'Mult':
                #array times n
                array = ir.left
                time = ir.right.value
                if not array.items:
                    raise RuntimeError('unsupported expression')
                else:
                    array.items = [item.clone() for item in array.items * time]
                return array
            else:
                print(error_info(ir.lineno))
                raise RuntimeError('multiplier for the list must be a constant')

        if suppress:
            return ir
        sym = self.scope.add_temp(Symbol.temp_prefix)
        mv = MOVE(TEMP(sym, Ctx.STORE), ir)
        mv.lineno = ir.lineno
        assert mv.lineno >= 0
        self.new_stms.append(mv)
        return TEMP(sym, Ctx.LOAD)

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        sym = self.scope.add_temp(Symbol.condition_prefix)
        mv = MOVE(TEMP(sym, Ctx.STORE), ir)
        mv.lineno = ir.lineno
        assert mv.lineno >= 0
        self.new_stms.append(mv)
        return TEMP(sym, Ctx.LOAD)

    def _has_return_type(self, ir):
        if ir.is_a(CALL):
            return True# ir.func_scope.return_type != Type.none_t
        elif ir.is_a(SYSCALL):
            return builtin_return_type_table[ir.name] != Type.none_t

    def _visit_args(self, ir):
        for i in range(len(ir.args)):
            ir.args[i] = self.visit(ir.args[i])
            assert ir.args[i].is_a([TEMP, CONST, UNOP, ARRAY])
            if ir.args[i].is_a(ARRAY):
                sym = self.scope.add_temp(Symbol.temp_prefix)
                #sym.set_type(Type.list(Type.int_t, None))
                mv = MOVE(TEMP(sym, Ctx.STORE), ir.args[i])
                mv.lineno = ir.lineno
                assert mv.lineno >= 0
                self.new_stms.append(mv)
                ir.args[i] = TEMP(sym, Ctx.LOAD)

    def visit_CALL(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        self._visit_args(ir)

        if suppress or not self._has_return_type(ir):
            return ir
        sym = self.scope.add_temp(Symbol.temp_prefix)
        mv = MOVE(TEMP(sym, Ctx.STORE), ir)
        mv.lineno = ir.lineno
        assert mv.lineno >= 0
        self.new_stms.append(mv)
        return TEMP(sym, Ctx.LOAD)

    def visit_SYSCALL(self, ir):
        return self.visit_CALL(ir)

    def visit_CTOR(self, ir):
        return self.visit_CALL(ir)

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.offset = self.visit(ir.offset)
        assert ir.offset.is_a([TEMP, ATTR, CONST, UNOP])

        if not suppress and ir.ctx & Ctx.LOAD:
            sym = self.scope.add_temp(Symbol.temp_prefix)
            mv = MOVE(TEMP(sym, Ctx.STORE), ir)
            mv.lineno = ir.lineno
            assert mv.lineno >= 0
            self.new_stms.append(mv)
            return TEMP(sym, Ctx.LOAD)
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
        if ir.src.is_a([BINOP, CALL, SYSCALL, CTOR, MREF]):
            self.suppress_converting = True
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        assert ir.src.is_a([TEMP, ATTR, CONST, UNOP, BINOP, MREF, MSTORE, CALL, CTOR, SYSCALL, ARRAY])
        assert ir.dst.is_a([TEMP, ATTR, MREF])

        if ir.dst.is_a(MREF):
            # For the sake of the memory analysis,
            # the assign to a item of a list is formed
            # @mem = mstore(@mem, idx, value)
            # instead of
            # mref(@mem, index) = value
            mref = ir.dst
            mref.mem.ctx = Ctx.LOAD
            ir.src = MSTORE(mref.mem, mref.offset, self.visit(ir.src))
            ir.dst = TEMP(mref.mem.sym, Ctx.STORE)
            ir.src.lineno = ir.lineno
            ir.dst.lineno = ir.lineno
        self.new_stms.append(ir)

