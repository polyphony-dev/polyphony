from collections import deque, defaultdict
from varreplacer import VarReplacer
from ir import CONST, TEMP, ARRAY, CALL, EXPR, MREF, MSTORE, MOVE
from symbol import Symbol
from scope import MemInfo
from type import Type
from irvisitor import IRTransformer
from logging import getLogger
logger = getLogger(__name__)
import pdb

class MemoryInfoMaker(IRTransformer):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        #transform array
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
        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        return ir

    def visit_CALL(self, ir):
        for i in range(len(ir.args)):
            ir.args[i] = self.visit(ir.args[i])
        return ir

    def visit_SYSCALL(self, ir):
        return self.visit_CALL(ir)

    def visit_CONST(self, ir):
        return ir

    def visit_MREF(self, ir):
        ir.offset = self.visit(ir.offset)
        ir.mem = self.visit(ir.mem)
        return ir

    def visit_MSTORE(self, ir):
        ir.offset = self.visit(ir.offset)
        ir.mem = self.visit(ir.mem)
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_ARRAY(self, ir):
        for i in range(len(ir.items)):
            ir.items[i] = self.visit(ir.items[i])
        return ir

    def visit_TEMP(self, ir):
        return ir

    def visit_EXPR(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MCJUMP(self, ir):
        for i in range(len(ir.conds)):
            ir.conds[i] = self.visit(ir.conds[i])
        self.new_stms.append(ir)

    def visit_JUMP(self, ir):
        self.new_stms.append(ir)

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)
        self.new_stms.append(ir)

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)

        if isinstance(ir.src, ARRAY):
            assert isinstance(ir.dst, TEMP)
            sym = self.scope.add_temp(Symbol.mem_prefix+'_'+ir.dst.sym.name+'_')
            sym.set_type(Type.list_int_t)
            mv = MOVE(TEMP(sym, 'Store'), ir.src)
            self.new_stms.append(mv)
            self.scope.meminfos[sym] = MemInfo(sym, len(ir.src.items), self.scope)
            ir.src = TEMP(sym, 'Load')
        self.new_stms.append(ir)


class MemoryTransformer:
    def process(self, scope):
        self.mem_moves = defaultdict(list)

        self._rename_mrefs(scope)
        self._detect_rom(scope)


    def _collect_def_mem_stm(self, scope):
        stms = []
        for block in scope.blocks:
            for stm in block.stms:
                if isinstance(stm, MOVE):
                    if stm.dst.sym.is_memory():
                        stms.append(stm)
        return stms

    def _collect_def_mem_and_call_stm(self, scope):
        stms = []
        for block in scope.blocks:
            for stm in block.stms:
                if isinstance(stm, MOVE):
                    if stm.dst.sym.is_memory():
                        stms.append((stm, stm.dst.sym))
                    if isinstance(stm.src, CALL):
                        for arg in stm.src.args:
                            if isinstance(arg, TEMP):
                                if arg.sym.is_memory():
                                    stms.append((stm, arg.sym))
                elif isinstance(stm, EXPR):
                    if isinstance(stm.exp, CALL):
                        for arg in stm.exp.args:
                            if isinstance(arg, TEMP):
                                if arg.sym.is_memory():
                                    stms.append((stm, arg.sym))
        return stms

    def _rename_mrefs(self, scope):
        usedef = scope.usedef
        worklist = deque()
        stms = self._collect_def_mem_stm(scope)
        alias_map = {}
        for mv in stms:
            logger.debug('!!! mem def stm ' + str(mv))
            assert isinstance(mv.src, ARRAY) \
                or (isinstance(mv.src, TEMP) and mv.src.sym.name.startswith('@in'))
            uses = usedef.get_sym_uses_stm(mv.dst.sym)
            worklist.extend(list(uses))

        while worklist:
            mv = worklist.popleft()
            if isinstance(mv, MOVE):
                if isinstance(mv.src, TEMP):
                    # check for list aliasing
                    if mv.dst.sym not in alias_map:
                        alias_map[mv.dst.sym] = mv.src.sym
                    else:
                        pass
                        #raise TypeError('list aliasing is not allowed')
                    mv.block.stms.remove(mv)
                    replaces = VarReplacer.replace_uses(mv.dst, mv.src, usedef)
                    worklist.extend(replaces)
                    usedef.remove_var_def(mv.dst, mv)
                    usedef.remove_use(mv.src, mv)
                elif isinstance(mv.src, MSTORE):
                    usedef.remove_var_def(mv.dst, mv)
                    replaces = VarReplacer.replace_uses(mv.dst, mv.src.mem, usedef)
                    worklist.extend(replaces)
                    mv.dst = TEMP(mv.src.mem.sym, 'Store')
                    usedef.add_var_def(mv.dst, mv)
            elif isinstance(mv, EXPR):
                pass
        for mv in stms:
            if not isinstance(mv.src, ARRAY):
                mv.block.stms.remove(mv)

    def _detect_rom(self, scope):
        shared_mem = set()
        stms = self._collect_def_mem_and_call_stm(scope)
        for stm, sym in stms:
            if isinstance(stm, EXPR):
                assert sym in scope.meminfos
                shared_mem.add(sym)

        for stm, sym in stms:
            if isinstance(stm, MOVE):
                self.mem_moves[sym].append(stm)

        for sym, mvs in self.mem_moves.items():
            stored = False
            constant = True
            for mv in mvs:
                if isinstance(mv.src, ARRAY):
                    for item in mv.src.items:
                        if not isinstance(item, CONST):
                            constant = False
                            break
                    scope.meminfos[sym].initstm = mv
                elif isinstance(mv.src, MSTORE):
                    stored = True
                    break
                elif isinstance(mv.src, CALL):
                    stored = True
                    break
            assert sym in scope.meminfos
            if (not stored) and constant and (sym not in shared_mem):
                scope.meminfos[sym].rom = True

