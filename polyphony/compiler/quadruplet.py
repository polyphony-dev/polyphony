from .ir import UNOP, BINOP, RELOP, CALL, SYSCALL, CONST, MREF, MSTORE, ARRAY, TEMP, EXPR, CJUMP, MCJUMP, JUMP, MOVE
from .common import funclog
from .symbol import Symbol
from .irvisitor import IRTransformer
from .type import Type
from .typecheck import builtin_return_type_table

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
        assert isinstance(ir.exp, TEMP) or isinstance(ir.exp, CONST) or isinstance(ir.exp, MREF)
        return ir

    def visit_BINOP(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)

        assert isinstance(ir.left, TEMP) or isinstance(ir.left, CONST) or isinstance(ir.left, UNOP) or isinstance(ir.left, MREF) or isinstance(ir.left, ARRAY)
        assert isinstance(ir.right, TEMP) or isinstance(ir.right, CONST) or isinstance(ir.right, UNOP) or isinstance(ir.right, MREF)

        if isinstance(ir.left, ARRAY):
            if isinstance(ir.right, CONST) and ir.op == 'Mult':
                #array times n
                array = ir.left
                time = ir.right.value
                if not array.items:
                    raise RuntimeError('unsupported expression')
                else:
                    array.items = [item.clone() for item in array.items * time]
                return array
            else:
                raise RuntimeError('unsupported expression')

        if suppress:
            return ir
        sym = self.scope.add_temp(Symbol.temp_prefix)
        mv = MOVE(TEMP(sym, 'Store'), ir)
        mv.lineno = ir.lineno
        self.new_stms.append(mv)
        return TEMP(sym, 'Load')

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        sym = self.scope.add_temp(Symbol.condition_prefix)
        mv = MOVE(TEMP(sym, 'Store'), ir)
        mv.lineno = ir.lineno
        self.new_stms.append(mv)
        return TEMP(sym, 'Load')

    def _has_return_type(self, ir):
        if isinstance(ir, CALL):
            return ir.func_scope.return_type != Type.none_t
        elif isinstance(ir, SYSCALL):
            return builtin_return_type_table[ir.name] != Type.none_t

    def visit_CALL(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        for i in range(len(ir.args)):
            ir.args[i] = self.visit(ir.args[i])
            assert isinstance(ir.args[i], TEMP) or isinstance(ir.args[i], CONST) or isinstance(ir.args[i], UNOP)

        if suppress or not self._has_return_type(ir):
            return ir
        sym = self.scope.add_temp(Symbol.temp_prefix)
        mv = MOVE(TEMP(sym, 'Store'), ir)
        mv.lineno = ir.lineno
        self.new_stms.append(mv)
        return TEMP(sym, 'Load')

    def visit_SYSCALL(self, ir):
        return self.visit_CALL(ir)

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        #suppress converting
        suppress = self.suppress_converting
        self.suppress_converting = False

        ir.offset = self.visit(ir.offset)
        assert isinstance(ir.offset, TEMP) or isinstance(ir.offset, CONST) or isinstance(ir.offset, UNOP)

        if not suppress and ir.ctx == 'Load':
            sym = self.scope.add_temp(Symbol.temp_prefix)
            mv = MOVE(TEMP(sym, 'Store'), ir)
            mv.lineno = ir.lineno
            self.new_stms.append(mv)
            return TEMP(sym, 'Load')
        return ir

    def visit_MSTORE(self, ir):
        return ir

    def visit_ARRAY(self, ir):
        for i in range(len(ir.items)):
            ir.items[i] = self.visit(ir.items[i])
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_EXPR(self, ir):
        #We don't convert outermost CALL
        if isinstance(ir.exp, CALL) or isinstance(ir.exp, SYSCALL):
            self.suppress_converting = True
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        assert isinstance(ir.exp, TEMP) and ir.exp.sym.is_condition() or isinstance(ir.exp, CONST)
        self.new_stms.append(ir)

    def visit_MCJUMP(self, ir):
        for i in range(len(ir.conds)):
            ir.conds[i] = self.visit(ir.conds[i])
            assert isinstance(ir.conds[i], TEMP) or isinstance(ir.conds[i], CONST)
        self.new_stms.append(ir)

    def visit_JUMP(self, ir):
        self.new_stms.append(ir)

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MOVE(self, ir):
        #We don't convert outermost BINOP or CALL
        if isinstance(ir.src, BINOP) or isinstance(ir.src, CALL) or isinstance(ir.src, SYSCALL) or isinstance(ir.src, MREF):
            self.suppress_converting = True
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        assert isinstance(ir.src, TEMP) or isinstance(ir.src, CONST) or isinstance(ir.src, UNOP) or isinstance(ir.src, BINOP) or isinstance(ir.src, MREF) or isinstance(ir.src, MSTORE) or isinstance(ir.src, CALL) or isinstance(ir.src, SYSCALL) or isinstance(ir.src, ARRAY)
        assert isinstance(ir.dst, TEMP) or isinstance(ir.dst, MREF)

        if isinstance(ir.dst, MREF):
            # For the sake of the memory analysis,
            # the assign to a item of a list is formed
            # @mem = mstore(@mem, idx, value)
            # instead of
            # mref(@mem, index) = value
            mref = ir.dst
            mref.mem.ctx = 'Load'
            ir.src = MSTORE(mref.mem, mref.offset, self.visit(ir.src))
            ir.dst = TEMP(mref.mem.sym, 'Store')
        self.new_stms.append(ir)

