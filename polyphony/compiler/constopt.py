from collections import deque
from .common import fail
from .errors import Errors
from .irvisitor import IRVisitor
from .ir import *
from .env import env
from .usedef import UseDefDetector
from .varreplacer import VarReplacer
from .dominator import DominatorTreeBuilder
from .scope import Scope
from .utils import *


def eval_unop(ir, ctx):
    op = ir.op
    v = ir.exp.value
    if op == 'Invert':
        return ~v
    elif op == 'Not':
        return 1 if (not v) is True else 0
    elif op == 'UAdd':
        return v
    elif op == 'USub':
        return -v
    else:
        fail(ctx.current_stm, Errors.UNSUPPORTED_OPERATOR, [op])


def eval_binop(ir, ctx):
    op = ir.op
    lv = ir.left.value
    rv = ir.right.value
    if op == 'Add':
        return lv + rv
    elif op == 'Sub':
        return lv - rv
    elif op == 'Mult':
        return lv * rv
    elif op == 'FloorDiv':
        return lv // rv
    elif op == 'Mod':
        return lv % rv
    elif op == 'Mod':
        return lv % rv
    elif op == 'LShift':
        return lv << rv
    elif op == 'RShift':
        return lv >> rv
    elif op == 'BitOr':
        return lv | rv
    elif op == 'BitXor':
        return lv ^ rv
    elif op == 'BitAnd':
        return lv & rv
    else:
        fail(ctx.current_stm, Errors.UNSUPPORTED_OPERATOR, [op])


def eval_relop(op, lv, rv, ctx):
    if op == 'Eq':
        b = lv == rv
    elif op == 'NotEq':
        b = lv != rv
    elif op == 'Lt':
        b = lv < rv
    elif op == 'LtE':
        b = lv <= rv
    elif op == 'Gt':
        b = lv > rv
    elif op == 'GtE':
        b = lv >= rv
    elif op == 'Is':
        b = lv is rv
    elif op == 'IsNot':
        b = lv is not rv
    elif op == 'And':
        b = lv and rv
    elif op == 'Or':
        b = lv or rv
    else:
        fail(ctx.current_stm, Errors.UNSUPPORTED_OPERATOR, [op])
    return 1 if b else 0


def try_get_constant(sym, scope):
    assert scope.usedef
    if sym.ancestor:
        sym = sym.ancestor
    defstms = scope.usedef.get_stms_defining(sym)
    if not defstms:
        defstms = sym.scope.usedef.get_stms_defining(sym)
        if not defstms:
            return None
    defstm = sorted(defstms, key=lambda s: s.program_order())[-1]
    if not defstm.is_a(MOVE):
        return None
    if not defstm.src.is_a(CONST):
        return None
    return defstm.src


class ConstantOptBase(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        if ir.exp.is_a(CONST):
            return CONST(eval_unop(ir, self))
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            return CONST(eval_binop(ir, self))
        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            return CONST(eval_relop(ir.op, ir.left.value, ir.right.value, self))
        elif (ir.left.is_a(CONST) or ir.right.is_a(CONST)) and (ir.op == 'And' or ir.op == 'Or'):
            const, var = (ir.left.value, ir.right) if ir.left.is_a(CONST) else (ir.right.value, ir.left)
            if ir.op == 'And':
                if const:
                    return var
                else:
                    return CONST(False)
            elif ir.op == 'Or':
                if const:
                    return CONST(True)
                else:
                    return var
        elif (ir.left.is_a([TEMP, ATTR])
                and ir.right.is_a([TEMP, ATTR])
                and ir.left.qualified_symbol() == ir.right.qualified_symbol()):
            c = CONST(eval_relop(ir.op, ir.left.symbol().id, ir.right.symbol().id, self))
            return c
        return ir

    def visit_CONDOP(self, ir):
        ir.cond = self.visit(ir.cond)
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.cond.is_a(CONST):
            if ir.cond.value:
                return ir.left
            else:
                return ir.right
        return ir

    def visit_CALL(self, ir):
        ir.args = [(name, self.visit(arg)) for name, arg in ir.args]
        if (ir.is_a(CALL)
                and ir.func.symbol().typ.is_function()
                and ir.func.symbol().typ.get_scope().is_lib()
                and ir.func.symbol().name == 'is_worker_running'):
            return CONST(True)
        return ir

    def visit_SYSCALL(self, ir):
        return self.visit_CALL(ir)

    def visit_NEW(self, ir):
        return self.visit_CALL(ir)

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)
        return ir

    def visit_MSTORE(self, ir):
        ir.offset = self.visit(ir.offset)
        return ir

    def visit_ARRAY(self, ir):
        ir.repeat = self.visit(ir.repeat)
        ir.items = [self.visit(item) for item in ir.items]
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_ATTR(self, ir):
        return ir

    def visit_EXPR(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        ir.conds = [self.visit(cond) for cond in ir.conds]

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)

    def visit_PHI(self, ir):
        # TODO: loop-phi
        #ir.ps = [self.visit(p) for p in ir.ps]
        pass


class ConstantOpt(ConstantOptBase):
    def __init__(self):
        super().__init__()
        self.mrg = env.memref_graph

    def process(self, scope):
        if scope.is_class():
            return
        self.scope = scope
        self.dtree = DominatorTreeBuilder(self.scope).process()

        dead_stms = []
        worklist = deque()
        for blk in scope.traverse_blocks():
            worklist.extend(blk.stms)
        while worklist:
            stm = worklist.popleft()
            self.current_stm = stm
            self.visit(stm)
            if stm.is_a(PHI):
                for i, p in enumerate(stm.ps[:]):
                    if p.is_a(CONST) and not p.value:
                        stm.ps.pop(i)
                        stm.args.pop(i)
                        stm.defblks.pop(i)
                if len(stm.args) == 1:
                    arg = stm.args[0]
                    blk = stm.defblks[0]
                    mv = MOVE(stm.var, arg)
                    blk.insert_stm(-1, mv)
                    worklist.append(mv)
                    dead_stms.append(stm)
                    if stm in worklist:
                        worklist.remove(stm)
            if (stm.is_a(MOVE)
                    and stm.src.is_a(CONST)
                    and stm.dst.is_a(TEMP)
                    and not stm.dst.sym.is_return()):
                #sanity check
                defstms = scope.usedef.get_stms_defining(stm.dst.symbol())
                assert len(defstms) <= 1

                replaces = VarReplacer.replace_uses(stm.dst, stm.src, scope.usedef)
                worklist.extend(replaces)
                worklist = deque(unique(worklist))
                scope.usedef.remove_var_def(stm.dst, stm)
                scope.del_sym(stm.dst.symbol())
                dead_stms.append(stm)
                if stm in worklist:
                    worklist.remove(stm)
            elif stm.is_a(CJUMP) and stm.exp.is_a(CONST):
                self._process_uncoditional_cjump(stm, worklist)
        for stm in dead_stms:
            if stm in stm.block.stms:
                stm.block.stms.remove(stm)

    #def _propagate_const(self, dst, const):

    def _process_uncoditional_cjump(self, cjump, worklist):
        def remove_dominated_branch(blk):
            blk.preds = []  # mark as garbage block
            remove_from_list(worklist, blk.stms)
            for succ in blk.succs:
                succ.preds.remove(blk)
            for succ in (succ for succ in blk.succs if succ not in blk.succs_loop):
                if self.dtree.is_child(blk, succ):
                    remove_dominated_branch(succ)

        blk = cjump.block
        if cjump.exp.value:
            true_blk = blk.succs[0]
            false_blk = blk.succs[1]
        else:
            true_blk = blk.succs[1]
            false_blk = blk.succs[0]
        jump = JUMP(true_blk)

        false_blk.preds.remove(blk)
        blk.succs.remove(false_blk)
        if self.scope.exit_block is false_blk:
            self.scope.exit_block = blk
        if not false_blk.preds and self.dtree.is_child(blk, false_blk):
            remove_dominated_branch(false_blk)

        blk.replace_stm(cjump, jump)
        if cjump in worklist:
            worklist.remove(cjump)

    def visit_SYSCALL(self, ir):
        if ir.sym.name == 'len':
            _, mem = ir.args[0]
            if mem.symbol().scope is Scope.global_scope():
                memsym = mem.symbol().ancestor
            else:
                memsym = mem.symbol()
            memnode = self.mrg.node(memsym)
            lens = []
            assert memnode
            for source in memnode.sources():
                lens.append(source.length)
            if len(lens) <= 1 or all(lens[0] == len for len in lens):
                assert lens[0] > 0
                return CONST(lens[0])
        return self.visit_CALL(ir)

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)
        memnode = ir.mem.symbol().typ.get_memnode()

        if ir.offset.is_a(CONST) and not memnode.is_writable():
            source = memnode.single_source()
            if source:
                assert source.initstm
                if not source.initstm.src.repeat.is_a(CONST):
                    fail(self.current_stm, Errors.SEQ_MULTIPLIER_MUST_BE_CONST)
                items = source.initstm.src.items * source.initstm.src.repeat.value
                return items[ir.offset.value]
        return ir

    def visit_TEMP(self, ir):
        if (ir.sym.scope is not self.scope
                and ir.sym.scope.is_global()
                and ir.sym.typ.is_scalar()):
            c = try_get_constant(ir.sym, ir.sym.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        return ir

    def visit_ATTR(self, ir):
        receiver = ir.tail()
        if receiver.typ.is_class() or receiver.typ.is_namespace():
            c = try_get_constant(ir.attr, ir.attr_scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.CLASS_VAR_MUST_BE_CONST)
        return ir

    def visit_PHI(self, ir):
        super().visit_PHI(ir)
        if len(ir.block.preds) != len(ir.args):
            remove_args = []
            for arg, blk in zip(ir.args, ir.defblks):
                if blk and blk is not self.scope.entry_block and not blk.preds:
                    remove_args.append(arg)
            for arg in remove_args:
                ir.remove_arg(arg)


class EarlyConstantOptNonSSA(ConstantOptBase):
    def __init__(self):
        super().__init__()

    def visit_TEMP(self, ir):
        if ir.sym.scope.is_namespace():
            c = try_get_constant(ir.sym, ir.sym.scope)
            if c:
                return c
        return ir

    def visit_ATTR(self, ir):
        receiver = ir.tail()
        if receiver.typ.is_class() or receiver.typ.is_namespace():
            c = try_get_constant(ir.attr, ir.attr_scope)
            if c:
                return c
        return ir


class ConstantOptPreDetectROM(ConstantOpt):
    def __init__(self):
        super().__init__()

    def visit_SYSCALL(self, ir):
        return self.visit_CALL(ir)

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)
        return ir

    def visit_TEMP(self, ir):
        if ir.sym.scope is not self.scope:
            c = try_get_constant(ir.sym, ir.sym.scope)
            if c:
                return c
        return ir

    def visit_ATTR(self, ir):
        if ir.head().typ.is_class():
            c = try_get_constant(ir.attr, ir.attr_scope)
            if c:
                return c
        return ir

    def visit_PHI(self, ir):
        super().visit_PHI(ir)
        for i, arg in enumerate(ir.args):
            ir.args[i] = self.visit(arg)


class GlobalConstantOpt(ConstantOptBase):
    def __init__(self):
        super().__init__()
        self.assign_table = {}

    def process(self, scope):
        assert scope.is_namespace() or scope.is_class()
        self.scope = scope
        if scope.block_count > 1:
            raise RuntimeError('A control statement in the global scope is not allowed')
        super().process(scope)
        self._remove_dead_code()

    def _remove_dead_code(self):
        dead_stms = []
        udd = UseDefDetector()
        udd.process(self.scope)

        for sym in self.scope.symbols.values():
            defstms = self.scope.usedef.get_stms_defining(sym)
            if len(defstms) > 1:
                defstms = sorted(defstms, key=lambda s: s.program_order())
                for i in range(len(defstms) - 1):
                    dead_stms.append(defstms[i])
        for stm in dead_stms:
            if stm in stm.block.stms:
                stm.block.stms.remove(stm)
                self.scope.usedef.remove_var_def(stm.dst, stm)

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)
        if ir.offset.is_a(CONST):
            array = self.visit(ir.mem)
            if array.is_a(ARRAY):
                return array.items[ir.offset.value]
            else:
                print(error_info(self.scope, ir.lineno))
                raise RuntimeError('{} must be a sequence object'.format(ir.mem.symbol()))
        return ir

    def visit_TEMP(self, ir):
        if ir.sym in self.assign_table:
            return self.assign_table[ir.sym]
        return ir

    def visit_EXPR(self, ir):
        pass

    def visit_CJUMP(self, ir):
        print(error_info(self.scope, ir.lineno))
        raise RuntimeError('A control statement in the global scope is not allowed')

    def visit_MCJUMP(self, ir):
        print(error_info(self.scope, ir.lineno))
        raise RuntimeError('A control statement in the global scope is not allowed')

    def visit_JUMP(self, ir):
        print(error_info(self.scope, ir.lineno))
        raise RuntimeError('A control statement in the global scope is not allowed')

    def visit_RET(self, ir):
        print(error_info(self.scope, ir.lineno))
        raise RuntimeError('A return statement in the global scope is not allowed')

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        self.assign_table[ir.dst.symbol()] = ir.src

    def visit_PHI(self, ir):
        assert False
