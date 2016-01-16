from collections import deque
from irvisitor import IRVisitor
from ir import CONST, TEMP, JUMP, MOVE
from env import env
from usedef import UseDefDetector
from varreplacer import VarReplacer

class ConstantFolding(IRVisitor):
    def __init__(self, scope):
        super().__init__()
        self.scope = scope
        self.mrg = env.memref_graph
        self.modified_stms = set()
        self.global_scope = env.scopes['@top']

    def process_stm(self, stm):
        self.current_stm = stm
        return self.visit(stm)

    def process_global(self):
        '''for global scope'''
        assert self.global_scope
        udd = UseDefDetector()
        udd.process(self.global_scope)

        for blk in self.global_scope.blocks:
            worklist = deque()
            worklist.extend(blk.stms)
            while worklist:
                stm = worklist.popleft()
                self.current_stm = stm
                self.visit(stm)
                if isinstance(stm, MOVE) and isinstance(stm.src, CONST):
                    replaces = VarReplacer.replace_uses(stm.dst, stm.src, self.global_scope.usedef)
                    worklist.extend(replaces)

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        if isinstance(ir.exp, CONST):
            self.modified_stms.add(self.current_stm)
            return CONST(self.eval_unop(ir.op, ir.exp.value))
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)

        # x = c1 op c2 
        #   => x = c3
        if isinstance(ir.left, CONST) and isinstance(ir.right, CONST):
            self.modified_stms.add(self.current_stm)
            return CONST(self.eval_binop(ir.op, ir.left.value, ir.right.value))

        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if isinstance(ir.left, CONST) and isinstance(ir.right, CONST):
            self.modified_stms.add(self.current_stm)
            return CONST(self.eval_relop(ir.op, ir.left.value, ir.right.value))
        return ir

    def visit_CALL(self, ir):
        ir.args = [self.visit(arg) for arg in ir.args]
        return ir

    def visit_SYSCALL(self, ir):
        if env.compile_phase > env.PHASE_1 and ir.name == 'len':
            mem = ir.args[0]
            assert isinstance(mem, TEMP)
            memnode = self.mrg.node(mem.sym)
            lens = []
            for root in self.mrg.collect_node_roots(memnode):
                lens.append(root.length)
            if len(lens) <= 1 or all(lens[0] == len for len in lens):
                self.modified_stms.add(self.current_stm)
                assert lens[0] > 0
                return CONST(lens[0])
        return self.visit_CALL(ir)

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)
        return ir

    def visit_MSTORE(self, ir):
        ir.offset = self.visit(ir.offset)
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_ARRAY(self, ir):
        ir.items = [self.visit(item) for item in ir.items]
        return ir

    def visit_TEMP(self, ir):
        if self.scope is not self.global_scope and ir.sym.scope is self.global_scope:
            c = self._try_get_global_constant(ir.sym)
            if not c:
                raise RuntimeError('global variable is must assigned to constant value')
            self.modified_stms.add(self.current_stm)
            return c
        return ir

    def visit_EXPR(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_MCJUMP(self, ir):
        ir.conds = [self.visit(cond) for cond in ir.conds]
        return ir

    def visit_JUMP(self, ir):
        return ir

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        return ir

    def visit_PHI(self, ir):
        return ir

    def eval_unop(self, op, v):
        if op == 'Invert':
            return ~v
        elif op == 'Not':
            return 1 if (not v) is True else 0
        elif op == 'UAdd':
            return v
        elif op == 'USub':
            return -v
        else:
            raise RuntimeError('operator is not supported yet ' + op)

    def eval_binop(self, op, lv, rv):
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
            raise RuntimeError('operator is not supported yet ' + op)

    def eval_relop(self, op, lv, rv):
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
        else:
            raise RuntimeError('operator is not supported yet ' + op)

    def _try_get_global_constant(self, sym):
        if sym.ancestor:
            sym = sym.ancestor
        defstms = self.global_scope.usedef.get_sym_defs_stm(sym)
        if not defstms:
            return None
        defstm = sorted(defstms, key=lambda s: s.program_order())[-1]
        if not isinstance(defstm, MOVE):
            return None
        if not isinstance(defstm.src, CONST):
            return None
        return defstm.src

