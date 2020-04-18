from collections import deque, defaultdict
from .block import Block
from .common import fail
from .dominator import DominatorTreeBuilder
from .env import env
from .errors import Errors
from .irvisitor import IRVisitor, IRTransformer
from .ir import *
from .irhelper import expr2ir, reduce_relexp
from .irhelper import eval_unop, eval_binop, reduce_binop, eval_relop
from .usedef import UseDefDetector
from .usedef import UseDefUpdater
from .utils import *
from .varreplacer import VarReplacer
from logging import getLogger
logger = getLogger(__name__)


def _try_get_constant(qsym, scope):
    sym = qsym[-1]
    if sym.ancestor:
        sym = sym.ancestor
    if sym in sym.scope.constants:
        return sym.scope.constants[sym]
    return None


def _try_get_constant_pure(qsym, scope):
    def find_value(vars, names):
        if len(names) > 1:
            head = names[0]
            if head in vars:
                _vars = vars[head]
                assert isinstance(_vars, dict)
                return find_value(_vars, names[1:])
        else:
            name = names[0]
            if name in vars:
                return vars[name]
        return None
    vars = env.runtime_info.global_vars
    names = [sym if isinstance(sym, str) else sym.name for sym in qsym]
    if qsym[0].scope.is_global():
        names = ['__main__'] + names
    elif qsym[0].scope.is_namespace() and not qsym[0].scope.is_global():
        names = [qsym[0].scope.name] + names
    v = find_value(vars, names)
    if isinstance(v, dict) and not v:
        return None
    if v is not None:
        return expr2ir(v, scope=scope)
    return None


def try_get_constant(qsym, scope):
    if env.config.enable_pure:
        return _try_get_constant_pure(qsym, scope)
    else:
        return _try_get_constant(qsym, scope)


def _mask_bit(typ, const):
    assert typ.is_int()
    assert const.is_a(CONST)
    w = typ.get_width()
    mask = (1 << w) - 1
    return CONST(mask & const.value)


class ConstantOptBase(IRVisitor):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        Block.set_order(scope.entry_block, 0)
        self.dtree = DominatorTreeBuilder(scope).process()
        super().process(scope)

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        if ir.exp.is_a(CONST):
            v = eval_unop(ir.op, ir.exp.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return CONST(v)
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            v = eval_binop(ir.op, ir.left.value, ir.right.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return CONST(v)
        elif ir.left.is_a(CONST) or ir.right.is_a(CONST):
            return reduce_binop(ir)
        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            v = eval_relop(ir.op, ir.left.value, ir.right.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return CONST(v)
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
            v = eval_relop(ir.op, ir.left.symbol().id, ir.right.symbol().id)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return CONST(v)
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
        ir.exp = self.visit(ir.exp)
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
        if ir.exp.is_a(CONST):
            self._process_unconditional_jump(ir, [])

    def visit_MCJUMP(self, ir):
        ir.conds = [self.visit(cond) for cond in ir.conds]
        conds = [c.value for c in ir.conds if c.is_a(CONST)]
        if len(conds) == len(ir.conds) and conds.count(1) == 1:
            self._process_unconditional_jump(ir, [], conds)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)

    def visit_CEXPR(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_EXPR(ir)

    def visit_CMOVE(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_MOVE(ir)

    def visit_PHI(self, ir):
        # TODO: loop-phi
        pass

    def _remove_dominated_branch(self, blk, worklist):
        blk.preds = []  # mark as garbage block
        remove_from_list(worklist, blk.stms)
        logger.debug('remove block {}'.format(blk.name))
        for child in self.dtree.get_children_of(blk):
            self._remove_dominated_branch(child, worklist)
        for succ in blk.succs:
            if blk in succ.preds:
                idx = succ.preds.index(blk)
                succ.remove_pred(blk)
                if succ.preds:
                    phis = succ.collect_stms([PHI, LPHI])
                    for phi in phis:
                        phi.args.pop(idx)
                        phi.ps.pop(idx)
                elif succ is not self.scope.entry_block:
                    self._remove_dominated_branch(succ, worklist)

    def _process_unconditional_jump(self, cjump, worklist, conds=None):
        blk = cjump.block
        if not blk.preds and self.scope.entry_block is not blk:
            return
        logger.debug('unconditional block {}'.format(blk.name))

        if cjump.is_a(CJUMP):
            if cjump.exp.value:
                true_idx = 0
            else:
                true_idx = 1
            targets = [cjump.true, cjump.false]
        else:
            true_idx = conds.index(1)
            targets = cjump.targets[:]

        counts = defaultdict(int)
        targets_with_count = []
        for tgt in targets:
            targets_with_count.append((tgt, counts[tgt]))
            counts[tgt] += 1
        true_blk, true_i = targets_with_count[true_idx]
        targets_with_count = targets_with_count[:true_idx] + targets_with_count[true_idx + 1:]
        # It is necessary to reverse the order of the loop
        # to avoid breaking blk_i
        for false_blk, blk_i in reversed(targets_with_count):
            if false_blk.preds:
                idx = find_nth_item_index(false_blk.preds, blk, blk_i)
                assert idx >= 0
                false_blk.preds.pop(idx)
                phis = false_blk.collect_stms([PHI, LPHI])
                for phi in phis:
                    phi.args.pop(idx)
                    phi.ps.pop(idx)

            idx = find_nth_item_index(blk.succs, false_blk, blk_i)
            assert idx >= 0
            blk.succs.pop(idx)
            if self.scope.exit_block is false_blk and not false_blk.preds:
                self.scope.exit_block = blk
            preds = [p for p in false_blk.preds if p not in false_blk.preds_loop]
            if (not preds and
                    self.dtree.is_child(blk, false_blk)):
                self._remove_dominated_branch(false_blk, worklist)

        jump = JUMP(true_blk)
        jump.loc = cjump.loc
        blk.replace_stm(cjump, jump)
        if cjump in worklist:
            worklist.remove(cjump)
        logger.debug(self.scope)


class ConstantOpt(ConstantOptBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        if scope.is_class():
            return
        self.scope = scope
        self.dtree = DominatorTreeBuilder(scope).process()
        self.udupdater = UseDefUpdater(scope)

        dead_stms = []
        self.worklist = deque()
        for blk in scope.traverse_blocks():
            self.worklist.extend(blk.stms)
        while self.worklist:
            stm = self.worklist.popleft()
            while stm in self.worklist:
                self.worklist.remove(stm)
            self.current_stm = stm
            self.visit(stm)
            if stm.is_a(PHIBase):
                for i, p in enumerate(stm.ps[:]):
                    stm.ps[i] = reduce_relexp(p)
                is_move = False
                for p in stm.ps[:]:
                    if not stm.is_a(LPHI) and p.is_a(CONST) and p.value and stm.ps.index(p) != (len(stm.ps) - 1):
                        is_move = True
                        idx = stm.ps.index(p)
                        mv = MOVE(stm.var, stm.args[idx])
                        blk = stm.block
                        blk.insert_stm(blk.stms.index(stm), mv)
                        self.udupdater.update(stm, mv)
                        self.worklist.append(mv)
                        dead_stms.append(stm)
                        break
                for p in stm.ps[:]:
                    if (p.is_a(CONST) and not p.value or
                            p.is_a(UNOP) and p.op == 'Not' and p.exp.is_a(CONST) and p.exp.value):
                        idx = stm.ps.index(p)
                        stm.ps.pop(idx)
                        stm.args.pop(idx)
                if not is_move and len(stm.args) == 1:
                    arg = stm.args[0]
                    blk = stm.block
                    mv = MOVE(stm.var, arg)
                    blk.insert_stm(blk.stms.index(stm), mv)
                    self.udupdater.update(stm, mv)
                    self.worklist.append(mv)
                    dead_stms.append(stm)
                elif len(stm.args) == 0:
                    # the stm in unreachble block
                    dead_stms.append(stm)
            elif stm.is_a([CMOVE, CEXPR]):
                stm.cond = reduce_relexp(stm.cond)
                if stm.cond.is_a(CONST):
                    if stm.cond.value:
                        blk = stm.block
                        if stm.is_a(CMOVE):
                            new_stm = MOVE(stm.dst, stm.src)
                        else:
                            new_stm = EXPR(stm.exp)
                        self.udupdater.update(stm, new_stm)
                        blk.insert_stm(blk.stms.index(stm), new_stm)
                    dead_stms.append(stm)
            elif (stm.is_a(MOVE)
                    and stm.src.is_a(CONST)
                    and stm.dst.is_a(TEMP)
                    and not stm.dst.symbol().is_return()):
                #sanity check
                defstms = scope.usedef.get_stms_defining(stm.dst.symbol())
                assert len(defstms) <= 1

                # TODO:
                #if stm.dst.symbol().typ.is_int() and isinstance(stm.src.value, int):
                #    src = _mask_bit(stm.dst.symbol().typ, stm.src)
                #else:
                #    src = stm.src
                replaces = VarReplacer.replace_uses(scope, stm.dst, stm.src)
                for rep in replaces:
                    if rep not in dead_stms:
                        self.worklist.append(rep)
                self.udupdater.update(stm, None)
                scope.del_sym(stm.dst.symbol().name)
                dead_stms.append(stm)
                if stm.dst.symbol().is_free():
                    for clos in stm.dst.symbol().scope.closures:
                        self._propagate_to_closure(clos, stm.dst, stm.src)
            elif (stm.is_a(MOVE)
                    and stm.src.is_a(CONST)
                    and stm.dst.is_a(ATTR)
                    and not stm.dst.symbol().is_return()):
                defstms = scope.usedef.get_stms_defining(stm.dst.symbol())
                if len(defstms) != 1:
                    continue
                replaces = VarReplacer.replace_uses(scope, stm.dst, stm.src)
                receiver = stm.dst.tail()
                if receiver.typ.is_object() and receiver.typ.get_scope().is_module():
                    module_scope = receiver.typ.get_scope()
                    assert self.scope.parent is module_scope
                    if module_scope.field_usedef:
                        defstms = module_scope.field_usedef.get_stms_defining(stm.dst.symbol())
                        if len(defstms) == 1:
                            module_scope.constants[stm.dst.symbol()] = stm.src
                for rep in replaces:
                    if rep not in dead_stms:
                        self.worklist.append(rep)
        for stm in dead_stms:
            if stm in stm.block.stms:
                stm.block.stms.remove(stm)

    def _propagate_to_closure(self, closure, dst, src):
        target = dst.symbol()
        UseDefDetector().process(closure)
        replaces = VarReplacer.replace_uses(closure, TEMP(target, Ctx.LOAD), src)
        # Consider the case self.scope is cloned
        if not replaces and self.scope.origin:
            orig_symbols = {cloned:orig for orig, cloned in self.scope.cloned_symbols.items()}
            if target in orig_symbols:
                target = orig_symbols[target]
                replaces = VarReplacer.replace_uses(closure, TEMP(target, Ctx.LOAD), src)

    def visit_SYSCALL(self, ir):
        if ir.sym.name == 'len':
            _, mem = ir.args[0]
            memsym = mem.symbol()
            assert memsym.typ.is_seq()
            length = memsym.typ.get_length()
            if length > 0:
                return CONST(length)
        return self.visit_CALL(ir)

    def visit_MREF(self, ir):
        if not ir.offset.is_a(CONST):
            return ir
        if ir.mem.symbol().scope.is_namespace() and ir.mem.symbol().typ.is_seq():
            array = try_get_constant(ir.mem.qualified_symbol(), self.scope)
            if array:
                c = array.items[ir.offset.value]
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        return ir


    def visit_TEMP(self, ir):
        if ir.sym.scope.is_namespace() and ir.sym.typ.is_scalar():
            c = try_get_constant(ir.qualified_symbol(), self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        return ir

    def visit_ATTR(self, ir):
        receiver = ir.tail()
        if (receiver.typ.is_class() or receiver.typ.is_namespace()) and ir.attr.typ.is_scalar():
            c = try_get_constant(ir.qualified_symbol(), self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        if receiver.typ.is_object() and ir.attr.typ.is_scalar():
            objscope = receiver.typ.get_scope()
            if objscope.is_class():
                classsym = objscope.parent.find_sym(objscope.base_name)
                if not classsym and objscope.is_instantiated():
                    objscope = objscope.origin
                    classsym = objscope.parent.find_sym(objscope.base_name)
                c = try_get_constant((classsym, ir.attr), self.scope)
                if c:
                    return c
        return ir

    def visit_PHI(self, ir):
        super().visit_PHI(ir)
        if not ir.block.is_hyperblock and len(ir.block.preds) != len(ir.args):
            remove_args = []
            for arg, blk in zip(ir.args, ir.block.preds):
                if blk and blk is not self.scope.entry_block and not blk.preds:
                    remove_args.append(arg)
            for arg in remove_args:
                ir.remove_arg(arg)

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        if ir.exp.is_a(CONST):
            self._process_unconditional_jump(ir, self.worklist)

    def visit_MCJUMP(self, ir):
        ir.conds = [self.visit(cond) for cond in ir.conds]
        conds = [c.value for c in ir.conds if c.is_a(CONST)]
        if len(conds) == len(ir.conds) and conds.count(1) == 1:
            self._process_unconditional_jump(ir, self.worklist, conds)


class EarlyConstantOptNonSSA(ConstantOptBase):
    def __init__(self):
        super().__init__()

    def visit_CJUMP(self, ir):
        ir.exp = self.visit(ir.exp)
        if ir.exp.is_a(CONST):
            self._process_unconditional_jump(ir, [])
            return
        expdefs = self.scope.usedef.get_stms_defining(ir.exp.symbol())
        assert len(expdefs) == 1
        expdef = list(expdefs)[0]
        if expdef.src.is_a(CONST):
            ir.exp = expdef.src
            self._process_unconditional_jump(ir, [])

    def visit_TEMP(self, ir):
        if ir.sym.scope.is_namespace() and ir.sym.typ.is_scalar():
            c = try_get_constant(ir.qualified_symbol(), self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        return ir

    def visit_ATTR(self, ir):
        receiver = ir.tail()
        if (receiver.typ.is_class() or receiver.typ.is_namespace()) and ir.attr.typ.is_scalar():
            c = try_get_constant(ir.qualified_symbol(), self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        if receiver.typ.is_object() and ir.attr.typ.is_scalar():
            objscope = receiver.typ.get_scope()
            if objscope.is_class():
                classsym = objscope.parent.find_sym(objscope.base_name)
                if not classsym and objscope.is_instantiated():
                    objscope = objscope.bases[0]
                    classsym = objscope.parent.find_sym(objscope.base_name)
                c = try_get_constant((classsym, ir.attr), self.scope)
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

    def visit_PHI(self, ir):
        super().visit_PHI(ir)
        for i, arg in enumerate(ir.args):
            ir.args[i] = self.visit(arg)


class PolyadConstantFolding(object):
    def process(self, scope):
        self.BinInlining().process(scope)
        self.Bin2Poly().process(scope)
        self.Poly2Bin().process(scope)

    class BinInlining(IRTransformer):
        @staticmethod
        def _can_inlining(usestm, ir):
            return (usestm.is_a(MOVE) and
                    usestm.src.is_a(BINOP) and
                    usestm.src.op == ir.src.op and
                    (usestm.src.left.is_a(CONST) or usestm.src.right.is_a(CONST)))

        def visit_MOVE(self, ir):
            self.new_stms.append(ir)
            if not ir.src.is_a(BINOP):
                return
            if not (ir.src.left.is_a(CONST) or ir.src.right.is_a(CONST)):
                return
            if ir.src.op not in ('Add', 'Mult'):
                return
            defstms = self.scope.usedef.get_stms_defining(ir.dst.symbol())
            if len(defstms) != 1:
                return
            usestms = self.scope.usedef.get_stms_using(ir.dst.symbol())
            for usestm in usestms:
                if self._can_inlining(usestm, ir):
                    usestm.replace(TEMP(ir.dst.symbol(), Ctx.LOAD), ir.src)

    class Bin2Poly(IRTransformer):
        def visit_BINOP(self, ir):
            ir.left = self.visit(ir.left)
            ir.right = self.visit(ir.right)
            assert ir.left and ir.right
            if ir.op in ('Add', 'Mult'):
                poly = POLYOP(ir.op)
                l = ir.left
                if l.is_a([BINOP, POLYOP]):
                    assert l.op == ir.op
                    poly.values.extend([e for e in l.kids()])
                else:
                    poly.values.append(l)

                r = ir.right
                if r.is_a([BINOP, POLYOP]):
                    assert l.op == ir.op
                    poly.values.extend([e for e in r.kids()])
                else:
                    poly.values.append(r)
                if len(poly.values) > 2:
                    return poly
            return ir

        def visit_POLYOP(self, ir):
            return ir

    class Poly2Bin(IRTransformer):
        @staticmethod
        def _fold(poly):
            vars = []
            consts = []
            for e in poly.values:
                if e.is_a(CONST):
                    consts.append(e)
                else:
                    vars.append(e)
            if poly.op == 'Add':
                const_result = 0
                for c in consts:
                    const_result += c.value
            elif poly.op == 'Mult':
                const_result = 1
                for c in consts:
                    const_result *= c.value
            poly.values = vars + [CONST(const_result)]

        def visit_POLYOP(self, ir):
            self._fold(ir)
            assert len(ir.values) == 2
            return BINOP(ir.op, ir.values[0], ir.values[1])


class StaticConstOpt(ConstantOptBase):
    def __init__(self):
        self.constant_table = {}
        self.constant_array_table = {}

    def process_scopes(self, scopes):
        stms = []
        dtrees = {}
        for s in scopes:
            stms.extend(self.collect_stms(s))
            Block.set_order(s.entry_block, 0)
            dtree = DominatorTreeBuilder(s).process()
            dtrees[s] = dtree
        # FIXME: Since lineno is not essential information for IR,
        #        It should not be used as sort key
        stms = sorted(stms, key=lambda s: s.loc.lineno)
        for stm in stms:
            self.current_stm = stm
            self.scope = stm.block.scope
            self.dtree = dtrees[stm.block.scope]
            self.visit(stm)
        for sym, c in self.constant_table.items():
            sym.scope.constants[sym] = c
        for sym, c in self.constant_array_table.items():
            sym.scope.constants[sym] = c

    def collect_stms(self, scope):
        stms = []
        for blk in scope.traverse_blocks():
            stms.extend(blk.stms)
        return stms

    def visit_TEMP(self, ir):
        if ir.sym in self.constant_table:
            return self.constant_table[ir.sym]
        return ir

    def visit_ATTR(self, ir):
        if ir.attr in self.constant_table:
            return self.constant_table[ir.attr]
        return ir

    def visit_MREF(self, ir):
        offs = self.visit(ir.offset)
        if ir.mem.symbol() in self.constant_array_table:
            array = self.constant_array_table[ir.mem.symbol()]
            return array.items[offs.value]
        return ir

    def visit_MOVE(self, ir):
        src = self.visit(ir.src)
        if ir.dst.is_a(TEMP):
            if src.is_a(CONST):
                self.constant_table[ir.dst.sym] = src
            elif src.is_a(ARRAY):
                self.constant_array_table[ir.dst.sym] = src
        ir.src = src


# from .typecheck import TypePropagation


# class RomDetector(TypePropagation):
#     def visit_ARRAY(self, ir):
#         if all(item.is_a(CONST) for item in ir.items):
#             ir.sym.typ.set_ro(True)
#         return ir.sym.typ

#     def visit_MOVE(self, ir):
#         # Do not overwrite other than the seq type
#         src_typ = self.visit(ir.src)
#         if ir.dst.is_a([TEMP, ATTR]) and ir.dst.symbol().typ.is_seq():
#             self._set_type(ir.dst.symbol(), src_typ.clone())
