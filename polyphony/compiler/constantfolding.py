from collections import deque, defaultdict
from .irvisitor import IRVisitor
from .ir import *
from .env import env
from .usedef import UseDefDetector
from .varreplacer import VarReplacer
from .type import Type
from .scope import Scope
from .common import error_info
import pdb


def eval_unop(ir):
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
        print(error_info(ir.lineno))
        raise RuntimeError('operator is not supported yet ' + op)

def eval_binop(ir):
    op = ir.op
    lv = ir.left.value
    rv = ir.right.value
    if op == 'Add':
        return lv + rv
    elif op == 'Sub':
        return lv - rv
    elif op == 'Mult':
        return lv * rv
    elif op == 'Div':
        return lv / rv
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
        print(error_info(ir.lineno))
        raise RuntimeError('operator is not supported yet ' + op)

def eval_relop(ir):
    op = ir.op
    lv = ir.left.value
    rv = ir.right.value
    if op == 'Eq':
        return lv == rv
    elif op == 'NotEq':
        return lv != rv
    elif op == 'Lt':
        return lv < rv
    elif op == 'LtE':
        return lv <= rv
    elif op == 'Gt':
        return lv > rv
    elif op == 'GtE':
        return lv >= rv
    elif op == 'Is':
        return lv is rv
    elif op == 'IsNot':
        return lv is not rv
    elif op == 'And':
        return lv and rv
    elif op == 'Or':
        return lv or rv
    else:
        print(error_info(ir.lineno))
        raise RuntimeError('operator is not supported yet ' + op)

def try_get_constant(sym, scope):
    assert scope.usedef
    if sym.ancestor:
        sym = sym.ancestor
    defstms = scope.usedef.get_def_stms_by_sym(sym)
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
            return CONST(eval_unop(ir))
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            return CONST(eval_binop(ir))
        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            return CONST(eval_relop(ir))
        return ir

    def visit_CALL(self, ir):
        ir.args = [self.visit(arg) for arg in ir.args]
        return ir

    def visit_SYSCALL(self, ir):
        return self.visit_CALL(ir)

    def visit_CTOR(self, ir):
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
        pass

class ConstantOpt(ConstantOptBase):
    def __init__(self):
        super().__init__()
        self.mrg = env.memref_graph

    def process(self, scope):
        if scope.is_class():
            return
        self.scope = scope
        dead_stms = []
        worklist = deque()
        for blk in scope.blocks:
            worklist.extend(blk.stms)
        while worklist:
            stm = worklist.popleft()
            self.current_stm = stm
            self.visit(stm)
            if stm.is_a(MOVE) and stm.src.is_a(CONST) and stm.dst.is_a(TEMP) and not stm.dst.sym.is_return():
                #sanity check
                defstms = scope.usedef.get_def_stms_by_sym(stm.dst.sym)
                assert len(defstms) <= 1

                replaces = VarReplacer.replace_uses(stm.dst, stm.src, scope.usedef)
                worklist.extend(replaces)
                scope.usedef.remove_var_def(stm.dst, stm)
                dead_stms.append(stm)
                if stm in worklist:
                    worklist.remove(stm)
        for stm in dead_stms:
            if stm in stm.block.stms:
                stm.block.stms.remove(stm)

    def visit_SYSCALL(self, ir):
        if ir.name == 'len':
            mem = ir.args[0]
            assert mem.is_a(TEMP)
            if mem.sym.scope is Scope.global_scope():
                memsym = mem.sym.ancestor
            else:
                memsym = mem.sym
            memnode = self.mrg.node(memsym)
            lens = []
            assert memnode
            for root in self.mrg.collect_node_roots(memnode):
                lens.append(root.length)
            if len(lens) <= 1 or all(lens[0] == len for len in lens):
                assert lens[0] > 0
                return CONST(lens[0])
        return self.visit_CALL(ir)

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)

        if ir.mem.is_a(TEMP):
            memnode = Type.extra(ir.mem.sym.typ)
        elif ir.mem.is_a(ATTR):
            memnode = Type.extra(ir.mem.attr.typ)

        if ir.offset.is_a(CONST) and not memnode.is_writable():
            root = self.mrg.get_single_root(memnode)
            if root:
                assert root.initstm
                return root.initstm.src.items[ir.offset.value]
        return ir

    def visit_TEMP(self, ir):
        if ir.sym.scope is not self.scope:
            c = try_get_constant(ir.sym, ir.sym.scope)
            if c:
                return c
            else:
                print(error_info(ir.lineno))
                raise RuntimeError('global variable is must assigned to constant value')
        return ir

    def visit_ATTR(self, ir):
        if Type.is_class(ir.head().typ):
            c = try_get_constant(ir.attr, ir.scope)
            if c:
                return c
            else:
                print(error_info(ir.lineno))
                raise RuntimeError('class variable is must assigned to constant value')
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
        if Type.is_class(ir.head().typ):
            c = try_get_constant(ir.attr, ir.scope)
            if c:
                return c
        return ir

class GlobalConstantOpt(ConstantOptBase):
    def __init__(self):
        super().__init__()
        self.assign_table = {}

    def process(self, scope):
        assert scope.is_global() or scope.is_class()
        self.scope = scope
        if len(scope.blocks) > 1:
            raise RuntimeError('A control statement in the global scope is not allowed')
        super().process(scope)
        self._remove_dead_code()

    def _remove_dead_code(self):
        dead_stms = []
        udd = UseDefDetector()
        udd.process(self.scope)

        for sym in self.scope.symbols.values():
            defstms = self.scope.usedef.get_def_stms_by_sym(sym)
            if len(defstms) > 1:
                defstms = sorted(defstms, key=lambda s: s.program_order())
                for i in range(len(defstms)-1):
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
                print(error_info(ir.lineno))
                raise RuntimeError('{} must be a sequence object'.format(ir.mem.sym.name))
        return ir

    def visit_TEMP(self, ir):
        if ir.sym in self.assign_table:
            return self.assign_table[ir.sym]
        return ir

    def visit_EXPR(self, ir):
        pass

    def visit_CJUMP(self, ir):
        print(error_info(ir.lineno))
        raise RuntimeError('A control statement in the global scope is not allowed')

    def visit_MCJUMP(self, ir):
        print(error_info(ir.lineno))
        raise RuntimeError('A control statement in the global scope is not allowed')

    def visit_JUMP(self, ir):
        print(error_info(ir.lineno))
        raise RuntimeError('A control statement in the global scope is not allowed')

    def visit_RET(self, ir):
        print(error_info(ir.lineno))
        raise RuntimeError('A return statement in the global scope is not allowed')

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        self.assign_table[ir.dst.sym] = ir.src

    def visit_PHI(self, ir):
        assert False
