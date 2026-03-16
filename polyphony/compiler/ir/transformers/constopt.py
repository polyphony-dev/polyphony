"""Constant optimization passes using new IR (ir.py).

NewConstantOptBase: shared constant folding logic.
NewEarlyConstantOptNonSSA: pre-SSA constant optimization.
NewConstantOpt: full constant optimization with worklist.
ConstantOptBase: old IR constant folding base (kept for PureFuncExecutor).
"""
from collections import defaultdict, deque
from ..block import Block
from ..ir import (
    Const, Temp, Attr, UnOp, BinOp, RelOp, CondOp, PolyOp,
    Call, SysCall, New, MRef, MStore, Array,
    Move, CMove, Expr, CExpr, CJump, MCJump, Jump,
    IrExp, IrVariable, IrNameExp, IrCallable, Phi, UPhi, LPhi,
    Ctx,
)
from ..ir_visitor import IrVisitor, IrTransformer
from ..ir_helper import (
    qualified_symbols, reduce_binop, reduce_relexp, irexp_type,
    eval_unop, eval_binop, eval_relop,
)
from ..symbol import Symbol
from ..types.type import Type
from ..analysis.dominator import DominatorTreeBuilder
from ..analysis.usedef import NewUseDefDetector, NewUseDefUpdater
from .varreplacer import NewVarReplacer
from ...common.common import fail
from ...common.errors import Errors
from ...common.env import env
from ...common.utils import find_nth_item_index, remove_from_list
from logging import getLogger
logger = getLogger(__name__)


# ============================================================
# ConstantOptBase (old IR, moved from constopt.py)
# ============================================================

from ..ir import CONST as OLD_CONST, IRVariable as OLD_IRVariable, JUMP as OLD_JUMP
from ..ir import CJUMP as OLD_CJUMP, PHI as OLD_PHI, LPHI as OLD_LPHI
from ..ir_visitor import IRVisitor as OldIRVisitor
from ..ir_helper import (
    qualified_symbols as old_qualified_symbols,
    reduce_relexp as old_reduce_relexp,
    eval_unop as old_eval_unop,
    eval_binop as old_eval_binop,
    reduce_binop as old_reduce_binop,
    eval_relop as old_eval_relop,
)
from ...common.utils import remove_from_list as _remove_from_list


class ConstantOptBase(OldIRVisitor):
    """Old IR constant folding base class, kept for PureFuncExecutor."""

    def __init__(self):
        super().__init__()

    def process(self, scope):
        Block.set_order(scope.entry_block, 0)
        self.dtree = DominatorTreeBuilder(scope).process()
        super().process(scope)

    def visit_UNOP(self, ir):
        ir.exp = self.visit(ir.exp)
        if isinstance(ir.exp, OLD_CONST):
            v = old_eval_unop(ir.op, ir.exp.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return OLD_CONST(v)
        return ir

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if isinstance(ir.left, OLD_CONST) and isinstance(ir.right, OLD_CONST):
            v = old_eval_binop(ir.op, ir.left.value, ir.right.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return OLD_CONST(v)
        elif isinstance(ir.left, OLD_CONST) or isinstance(ir.right, OLD_CONST):
            return old_reduce_binop(ir)
        return ir

    def visit_RELOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if isinstance(ir.left, OLD_CONST) and isinstance(ir.right, OLD_CONST):
            v = old_eval_relop(ir.op, ir.left.value, ir.right.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return OLD_CONST(v)
        elif (isinstance(ir.left, OLD_CONST) or isinstance(ir.right, OLD_CONST)) and (ir.op == 'And' or ir.op == 'Or'):
            const, var = (ir.left.value, ir.right) if isinstance(ir.left, OLD_CONST) else (ir.right.value, ir.left)
            if ir.op == 'And':
                if const:
                    return var
                else:
                    return OLD_CONST(False)
            elif ir.op == 'Or':
                if const:
                    return OLD_CONST(True)
                else:
                    return var
        elif (isinstance(ir.left, OLD_IRVariable)
                and isinstance(ir.right, OLD_IRVariable)
                and (left_qsym := old_qualified_symbols(ir.left, self.scope))
                and (right_qsym := old_qualified_symbols(ir.right, self.scope))
                and left_qsym == right_qsym):
            v = old_eval_relop(ir.op, left_qsym[-1].id, right_qsym[-1].id)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return OLD_CONST(v)
        return ir

    def visit_CONDOP(self, ir):
        ir.cond = self.visit(ir.cond)
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if isinstance(ir.cond, OLD_CONST):
            if ir.cond.value:
                return ir.left
            else:
                return ir.right
        return ir

    def visit_CALL(self, ir):
        ir.args = [(name, self.visit(arg)) for name, arg in ir.args]
        qsym = old_qualified_symbols(ir.func, self.scope)
        assert isinstance(qsym[-1], Symbol)
        func_t = qsym[-1].typ
        if (func_t.is_function()
                and func_t.scope.is_lib()
                and func_t.scope.base_name == 'is_worker_running'):
            return OLD_CONST(True)
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
        if isinstance(ir.exp, OLD_CONST):
            self._process_unconditional_jump(ir, [])

    def visit_MCJUMP(self, ir):
        ir.conds = [self.visit(cond) for cond in ir.conds]
        conds = [c.value for c in ir.conds if isinstance(c, OLD_CONST)]
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
        pass

    def _remove_dominated_branch(self, blk, worklist):
        blk.preds = []
        _remove_from_list(worklist, blk.stms)
        logger.debug('remove block {}'.format(blk.name))
        for child in self.dtree.get_children_of(blk):
            self._remove_dominated_branch(child, worklist)
        for succ in blk.succs:
            if blk in succ.preds:
                idx = succ.preds.index(blk)
                succ.remove_pred(blk)
                if succ.preds:
                    phis = succ.collect_stms(OLD_PHI)
                    for phi in phis:
                        for pi, p in enumerate(phi.ps[:]):
                            for v in p.find_irs(OLD_IRVariable):
                                v_sym = old_qualified_symbols(v, self.scope)[-1]
                                assert isinstance(v_sym, Symbol)
                                blks = self.usedef.get_blks_defining(v_sym)
                                if blk in blks:
                                    phi.args.pop(pi)
                                    phi.ps.pop(pi)
                                    break
                    lphis = succ.collect_stms(OLD_LPHI)
                    for lphi in lphis:
                        lphi.args.pop(idx)
                        lphi.ps.pop(idx)
                elif succ is not self.scope.entry_block:
                    self._remove_dominated_branch(succ, worklist)

    def _process_unconditional_jump(self, cjump, worklist, conds=None):
        blk = cjump.block
        if not blk.preds and self.scope.entry_block is not blk:
            return
        logger.debug('unconditional block {}'.format(blk.name))

        if isinstance(cjump, OLD_CJUMP):
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
        for false_blk, blk_i in reversed(targets_with_count):
            if false_blk.preds:
                idx = find_nth_item_index(false_blk.preds, blk, blk_i)
                assert idx >= 0
                false_blk.preds.pop(idx)
                phis = false_blk.collect_stms([OLD_PHI, OLD_LPHI])
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

        jump = OLD_JUMP(true_blk)
        jump.loc = cjump.loc
        blk.replace_stm(cjump, jump)
        if cjump in worklist:
            worklist.remove(cjump)
        logger.debug(self.scope)






def _try_get_constant_new(qsym, scope):
    """Get constant value as new IR Const (converts from old IR if needed)."""
    from ..ir_helper import try_get_constant
    c = try_get_constant(qsym, scope)
    if c is None:
        return None
    # c is old IR CONST, convert to new IR Const
    return c


class NewConstantOptBase(IrVisitor):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        Block.set_order(scope.entry_block, 0)
        self.dtree = DominatorTreeBuilder(scope).process()
        super().process(scope)

    def visit_UnOp(self, ir):
        ir.exp = self.visit(ir.exp)
        if isinstance(ir.exp, Const):
            v = eval_unop(ir.op, ir.exp.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return Const(value=v)
        return ir

    def visit_BinOp(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if isinstance(ir.left, Const) and isinstance(ir.right, Const):
            v = eval_binop(ir.op, ir.left.value, ir.right.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return Const(value=v)
        elif isinstance(ir.left, Const) or isinstance(ir.right, Const):
            return reduce_binop(ir)
        return ir

    def visit_RelOp(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if isinstance(ir.left, Const) and isinstance(ir.right, Const):
            v = eval_relop(ir.op, ir.left.value, ir.right.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return Const(value=v)
        elif (isinstance(ir.left, Const) or isinstance(ir.right, Const)) and (ir.op == 'And' or ir.op == 'Or'):
            const, var = (ir.left.value, ir.right) if isinstance(ir.left, Const) else (ir.right.value, ir.left)
            if ir.op == 'And':
                return var if const else Const(value=False)
            elif ir.op == 'Or':
                return Const(value=True) if const else var
        elif (isinstance(ir.left, IrVariable)
                and isinstance(ir.right, IrVariable)
                and (left_qsym := qualified_symbols(ir.left, self.scope))
                and (right_qsym := qualified_symbols(ir.right, self.scope))
                and left_qsym == right_qsym):
            v = eval_relop(ir.op, left_qsym[-1].id, right_qsym[-1].id)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return Const(value=v)
        return ir

    def visit_CondOp(self, ir):
        ir.cond = self.visit(ir.cond)
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if isinstance(ir.cond, Const):
            return ir.left if ir.cond.value else ir.right
        return ir

    def visit_Call(self, ir):
        ir.args = [(name, self.visit(arg)) for name, arg in ir.args]
        qsym = qualified_symbols(ir.func, self.scope)
        assert isinstance(qsym[-1], Symbol)
        func_t = qsym[-1].typ
        if (func_t.is_function()
                and func_t.scope.is_lib()
                and func_t.scope.base_name == 'is_worker_running'):
            return Const(value=True)
        return ir

    def visit_SysCall(self, ir):
        return self.visit_Call(ir)

    def visit_New(self, ir):
        return self.visit_Call(ir)

    def visit_Const(self, ir):
        return ir

    def visit_MRef(self, ir):
        ir.offset = self.visit(ir.offset)
        return ir

    def visit_MStore(self, ir):
        ir.offset = self.visit(ir.offset)
        ir.exp = self.visit(ir.exp)
        return ir

    def visit_Array(self, ir):
        ir.repeat = self.visit(ir.repeat)
        ir.items = [self.visit(item) for item in ir.items]
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_Attr(self, ir):
        return ir

    def visit_Expr(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_CJump(self, ir):
        ir.exp = self.visit(ir.exp)
        if isinstance(ir.exp, Const):
            self._process_unconditional_jump(ir, [])

    def visit_MCJump(self, ir):
        ir.conds = [self.visit(cond) for cond in ir.conds]
        conds = [c.value for c in ir.conds if isinstance(c, Const)]
        if len(conds) == len(ir.conds) and conds.count(1) == 1:
            self._process_unconditional_jump(ir, [], conds)

    def visit_Jump(self, ir):
        pass

    def visit_Ret(self, ir):
        ir.exp = self.visit(ir.exp)

    def visit_Move(self, ir):
        ir.src = self.visit(ir.src)

    def visit_CExpr(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_Expr(ir)

    def visit_CMove(self, ir):
        ir.cond = self.visit(ir.cond)
        self.visit_Move(ir)

    def visit_Phi(self, ir):
        pass

    def _remove_dominated_branch(self, blk, worklist):
        blk.preds = []
        remove_from_list(worklist, blk.stms)
        logger.debug('remove block {}'.format(blk.name))
        for child in self.dtree.get_children_of(blk):
            self._remove_dominated_branch(child, worklist)
        for succ in blk.succs:
            if blk in succ.preds:
                idx = succ.preds.index(blk)
                succ.remove_pred(blk)
                if succ.preds:
                    phis = succ.collect_stms([Phi])
                    for phi in phis:
                        for pi, p in enumerate(phi.ps[:]):
                            if isinstance(p, IrVariable):
                                v_sym = qualified_symbols(p, self.scope)[-1]
                                assert isinstance(v_sym, Symbol)
                                blks = self.usedef.get_blks_defining(v_sym)
                                if blk in blks:
                                    phi.args.pop(pi)
                                    phi.ps.pop(pi)
                                    break
                    lphis = succ.collect_stms([LPhi])
                    for lphi in lphis:
                        lphi.args.pop(idx)
                        lphi.ps.pop(idx)
                elif succ is not self.scope.entry_block:
                    self._remove_dominated_branch(succ, worklist)

    def _process_unconditional_jump(self, cjump, worklist, conds=None):
        blk = cjump.block
        if not blk.preds and self.scope.entry_block is not blk:
            return
        logger.debug('unconditional block {}'.format(blk.name))

        if isinstance(cjump, CJump):
            true_idx = 0 if cjump.exp.value else 1
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
        for false_blk, blk_i in reversed(targets_with_count):
            if false_blk.preds:
                idx = find_nth_item_index(false_blk.preds, blk, blk_i)
                assert idx >= 0
                false_blk.preds.pop(idx)
                phis = false_blk.collect_stms([Phi, LPhi])
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

        jump = Jump(target=true_blk, loc=cjump.loc, block=blk)
        blk.replace_stm(cjump, jump)
        if cjump in worklist:
            worklist.remove(cjump)
        logger.debug(str(self.scope))


class NewEarlyConstantOptNonSSA(NewConstantOptBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        self.usedef = NewUseDefDetector().process(scope)
        super().process(scope)

    def visit_CJump(self, ir):
        ir.exp = self.visit(ir.exp)
        if isinstance(ir.exp, Const):
            self._process_unconditional_jump(ir, [])
            return
        assert isinstance(ir.exp, IrVariable)
        exp_sym = qualified_symbols(ir.exp, self.scope)[-1]
        assert isinstance(exp_sym, Symbol)
        expdefs = self.usedef.get_stms_defining(exp_sym)
        assert len(expdefs) == 1
        expdef = list(expdefs)[0]
        if isinstance(expdef, Move) and isinstance(expdef.src, Const):
            ir.exp = expdef.src
            self._process_unconditional_jump(ir, [])

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym_t = sym.typ
        if sym.scope.is_containable() and sym_t.is_scalar():
            c = _try_get_constant_new((sym,), self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        return ir

    def visit_Attr(self, ir):
        qsyms = qualified_symbols(ir, self.scope)
        attr = qsyms[-1]
        receiver = qsyms[-2]
        assert isinstance(attr, Symbol)
        assert isinstance(receiver, Symbol)
        attr_t = attr.typ
        receiver_t = receiver.typ
        if (receiver_t.is_class() or receiver_t.is_namespace()) and attr_t.is_scalar():
            c = _try_get_constant_new(qsyms, self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        if receiver_t.is_object() and attr_t.is_scalar():
            objscope = receiver_t.scope
            if objscope.is_class():
                classsym = objscope.parent.find_sym(objscope.base_name)
                if not classsym and objscope.is_instantiated():
                    objscope = objscope.bases[0]
                    classsym = objscope.parent.find_sym(objscope.base_name)
                c = _try_get_constant_new((classsym, attr), self.scope)
                if c:
                    return c
        return ir


def _to_signed(typ, const):
    assert typ.is_int() and typ.signed is True
    assert isinstance(const, Const)
    from ..ir_helper import bits2int
    nbit = typ.width
    mask = (1 << nbit) - 1
    bits = (const.value & mask)
    return Const(value=bits2int(bits, nbit))


def _to_unsigned(typ, const):
    assert typ.is_int() and typ.signed is False
    assert isinstance(const, Const)
    nbit = typ.width
    mask = (1 << nbit) - 1
    return Const(value=const.value & mask)


class NewConstantOpt(NewConstantOptBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        if scope.is_class():
            return
        self.scope = scope
        self.dtree = DominatorTreeBuilder(scope).process()
        self.usedef = NewUseDefDetector().process(scope)
        self.udupdater = NewUseDefUpdater(scope, self.usedef)

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
            if isinstance(stm, (Phi, UPhi, LPhi)):
                for i, p in enumerate(stm.ps[:]):
                    stm.ps[i] = reduce_relexp(p)
                is_move = False
                for p in stm.ps[:]:
                    if not isinstance(stm, LPhi) and isinstance(p, Const) and p.value and stm.ps.index(p) != (len(stm.ps) - 1):
                        is_move = True
                        idx = stm.ps.index(p)
                        mv = Move(dst=stm.var, src=stm.args[idx], block=stm.block)
                        blk = stm.block
                        blk.stms.insert(blk.stms.index(stm), mv)
                        self.udupdater.update(stm, mv)
                        self.worklist.append(mv)
                        dead_stms.append(stm)
                        break
                for p in stm.ps[:]:
                    if (isinstance(p, Const) and not p.value or
                            isinstance(p, UnOp) and p.op == 'Not' and isinstance(p.exp, Const) and p.exp.value):
                        idx = stm.ps.index(p)
                        stm.ps.pop(idx)
                        stm.args.pop(idx)
                if not is_move and len(stm.args) == 1:
                    arg = stm.args[0]
                    blk = stm.block
                    mv = Move(dst=stm.var, src=arg, block=stm.block)
                    blk.stms.insert(blk.stms.index(stm), mv)
                    self.udupdater.update(stm, mv)
                    self.worklist.append(mv)
                    dead_stms.append(stm)
                elif len(stm.args) == 0:
                    dead_stms.append(stm)
            elif isinstance(stm, (CMove, CExpr)):
                stm.cond = reduce_relexp(stm.cond)
                if isinstance(stm.cond, Const):
                    if stm.cond.value:
                        blk = stm.block
                        if isinstance(stm, CMove):
                            new_stm = Move(dst=stm.dst, src=stm.src, block=blk)
                        else:
                            new_stm = Expr(exp=stm.exp, block=blk)
                        self.udupdater.update(stm, new_stm)
                        blk.stms.insert(blk.stms.index(stm), new_stm)
                    dead_stms.append(stm)
            elif (isinstance(stm, Move)
                    and isinstance(stm.src, Const)
                    and isinstance(stm.dst, Temp)
                    and (dst_sym := qualified_symbols(stm.dst, self.scope)[-1])
                    and not dst_sym.is_return()):
                assert isinstance(dst_sym, Symbol)
                defstms = self.usedef.get_stms_defining(dst_sym)
                assert len(defstms) <= 1

                dst_t = dst_sym.typ
                if dst_t.is_int() and isinstance(stm.src.value, int):
                    if dst_t.signed:
                        src = _to_signed(dst_t, stm.src)
                    else:
                        src = _to_unsigned(dst_t, stm.src)
                else:
                    src = stm.src
                replaces = NewVarReplacer.replace_uses(scope, stm.dst, src, self.usedef)
                for rep in replaces:
                    logger.debug(rep)
                    if rep not in dead_stms:
                        self.worklist.append(rep)
                self.udupdater.update(stm, None)
                dead_stms.append(stm)
                if dst_sym.is_free():
                    for clos in dst_sym.scope.closures():
                        self._propagate_to_closure(clos, dst_sym, stm.src)
            elif self._can_attribute_propagate(stm):
                dst_load = stm.dst.model_copy(update={'ctx': Ctx.LOAD})
                dst_store = stm.dst
                found_new_def = False
                for next_stm in list(self.worklist):
                    use_vars = self.usedef.get_vars_used_at(next_stm)
                    for v in use_vars:
                        if dst_load == v:
                            # Replace use in next_stm
                            replacer = NewVarReplacer(scope, dst_load, stm.src, self.usedef)
                            replacer.visit(next_stm)
                            break
                    def_vars = self.usedef.get_vars_defined_at(next_stm)
                    for v in def_vars:
                        if dst_store == v:
                            found_new_def = True
                            break
                    if found_new_def:
                        break
            elif (isinstance(stm, Move)
                    and isinstance(stm.src, Array)
                    and isinstance(stm.src.repeat, Const)):
                src = stm.src
                dst_sym = qualified_symbols(stm.dst, self.scope)[-1]
                array_t = dst_sym.typ
                assert array_t.is_seq()
                if array_t.length == Type.ANY_LENGTH:
                    dst_sym.typ = dst_sym.typ.clone(length=len(src.items) * src.repeat.value)
        for stm in dead_stms:
            if stm in stm.block.stms:
                stm.block.stms.remove(stm)

    def _can_attribute_propagate(self, stm):
        if not isinstance(stm, Move):
            return False
        if not isinstance(stm.src, Const):
            return False
        if not isinstance(stm.dst, Attr):
            return False
        if not self.scope.is_ctor():
            return False
        return True

    def _propagate_to_closure(self, closure, target, src):
        clos_usedef = NewUseDefDetector().process(closure)
        NewVarReplacer.replace_uses(closure, Temp(name=target.name), src, clos_usedef)

    def visit_SysCall(self, ir):
        if ir.name == 'len':
            _, mem = ir.args[0]
            mem_t = irexp_type(mem, self.scope)
            assert mem_t.is_seq()
            if mem_t.length != Type.ANY_LENGTH:
                return Const(value=mem_t.length)
            mem_qsym = qualified_symbols(mem, self.scope)
            array = _try_get_constant_new(mem_qsym, self.scope)
            if array and isinstance(array.repeat, Const):
                length = array.repeat.value * len(array.items)
                assert False  # TODO: check (same as old code)
                return Const(value=length)
        return self.visit_Call(ir)

    def visit_MRef(self, ir):
        if not isinstance(ir.offset, Const):
            return ir
        if isinstance(ir.mem, Array):
            offset = ir.offset.value
            if 0 <= offset < len(ir.mem.items):
                return ir.mem.items[offset]
            return ir
        if not isinstance(ir.mem, IrNameExp):
            return ir
        qsym = qualified_symbols(ir.mem, self.scope)
        mem_sym = qsym[-1]
        assert isinstance(mem_sym, Symbol)
        mem_t = mem_sym.typ
        if mem_sym.scope.is_containable() and mem_t.is_seq():
            array = _try_get_constant_new(qsym, self.scope)
            if array:
                return array.items[ir.offset.value]
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        return ir

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym_t = sym.typ
        if sym.scope.is_containable() and sym_t.is_scalar():
            c = _try_get_constant_new((sym,), self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        return ir

    def visit_Attr(self, ir):
        qsym = qualified_symbols(ir, self.scope)
        attr = qsym[-1]
        receiver = qsym[-2]
        assert isinstance(attr, Symbol)
        assert isinstance(receiver, Symbol)
        attr_t = attr.typ
        receiver_t = receiver.typ
        if (receiver_t.is_class() or receiver_t.is_namespace()) and attr_t.is_scalar():
            c = _try_get_constant_new(qsym, self.scope)
            if c:
                return c
            else:
                fail(self.current_stm, Errors.GLOBAL_VAR_MUST_BE_CONST)
        if receiver_t.is_object() and attr_t.is_scalar():
            objscope = receiver_t.scope
            if objscope.is_class():
                classsym = objscope.parent.find_sym(objscope.base_name)
                if not classsym and objscope.is_instantiated():
                    objscope = objscope.origin
                    classsym = objscope.parent.find_sym(objscope.base_name)
                c = _try_get_constant_new((classsym, attr), self.scope)
                if c:
                    return c
        return ir

    def visit_Phi(self, ir):
        super().visit_Phi(ir)
        if not ir.block.is_hyperblock and len(ir.block.preds) != len(ir.args):
            remove_args = []
            for arg, blk in zip(ir.args, ir.block.preds):
                if blk and blk is not self.scope.entry_block and not blk.preds:
                    remove_args.append(arg)
            for arg in remove_args:
                idx = ir.args.index(arg)
                ir.args.pop(idx)
                ir.ps.pop(idx)

    def visit_CJump(self, ir):
        ir.exp = self.visit(ir.exp)
        if isinstance(ir.exp, Const):
            self._process_unconditional_jump(ir, self.worklist)

    def visit_MCJump(self, ir):
        ir.conds = [self.visit(cond) for cond in ir.conds]
        conds = [c.value for c in ir.conds if isinstance(c, Const)]
        if len(conds) == len(ir.conds) and conds.count(1) == 1:
            self._process_unconditional_jump(ir, self.worklist, conds)


class NewStaticConstOpt(NewConstantOptBase):
    """Propagate static constants across scopes using new IR."""

    def __init__(self):
        self.constant_table: dict[Symbol, Const] = {}
        self.constant_array_table: dict[Symbol, Array] = {}

    def process_scopes(self, scopes):
        stms = []
        dtrees = {}
        for s in scopes:
            stms.extend(self._collect_stms(s))
            Block.set_order(s.entry_block, 0)
            dtree = DominatorTreeBuilder(s).process()
            dtrees[s] = dtree
        # Sort by line number (matches old behavior)
        stms = sorted(stms, key=lambda s: s.loc.lineno)
        for stm in stms:
            self.current_stm = stm
            self.scope = stm.block.scope
            self.dtree = dtrees[stm.block.scope]
            self.visit(stm)
        for sym, c in self.constant_table.items():
            sym.scope.constants[sym] = c
            if sym.scope.origin:
                origin_scope = sym.scope.origin
                if sym.name in origin_scope.symbols:
                    origin_scope.constants[origin_scope.symbols[sym.name]] = c
        for sym, c in self.constant_array_table.items():
            sym.scope.constants[sym] = c
            if sym.scope.origin:
                origin_scope = sym.scope.origin
                if sym.name in origin_scope.symbols:
                    origin_scope.constants[origin_scope.symbols[sym.name]] = c

    def _collect_stms(self, scope):
        stms = []
        for blk in scope.traverse_blocks():
            stms.extend(blk.stms)
        return stms

    def visit_Temp(self, ir):
        sym = qualified_symbols(ir, self.scope)[-1]
        if sym in self.constant_table:
            return self.constant_table[sym]
        return ir

    def visit_Attr(self, ir):
        sym = qualified_symbols(ir, self.scope)[-1]
        if sym in self.constant_table:
            return self.constant_table[sym]
        return ir

    def visit_MRef(self, ir):
        ir.offset = self.visit(ir.offset)
        if isinstance(ir.mem, IrVariable):
            mem_sym = qualified_symbols(ir.mem, self.scope)[-1]
            if mem_sym in self.constant_array_table:
                array = self.constant_array_table[mem_sym]
                if isinstance(ir.offset, Const):
                    return array.items[ir.offset.value]
        return ir

    def visit_Move(self, ir):
        src = self.visit(ir.src)
        dst_sym = qualified_symbols(ir.dst, self.scope)[-1]
        if isinstance(dst_sym, Symbol):
            if isinstance(src, Const):
                self.constant_table[dst_sym] = src
            elif isinstance(src, Array):
                self.constant_array_table[dst_sym] = src
        ir.src = src


class NewPolyadConstantFolding(object):
    """Convert binary ops to poliad ops and fold constants, using new IR."""

    def process(self, scope):
        self._BinInlining().process(scope)
        self._Bin2Poly().process(scope)
        self._Poly2Bin().process(scope)

    class _BinInlining(IrTransformer):
        def process(self, scope):
            from ..analysis.usedef import NewUseDefDetector
            self.usedef = NewUseDefDetector().process(scope)
            super().process(scope)

        @staticmethod
        def _can_inlining(usestm, ir):
            return (isinstance(usestm, Move) and
                    isinstance(usestm.src, BinOp) and
                    usestm.src.op == ir.src.op and
                    (isinstance(usestm.src.left, Const) or isinstance(usestm.src.right, Const)))

        def visit_Move(self, ir):
            self.new_stms.append(ir)
            if not isinstance(ir.src, BinOp):
                return
            if not (isinstance(ir.src.left, Const) or isinstance(ir.src.right, Const)):
                return
            if ir.src.op not in ('Add', 'Mult'):
                return
            assert isinstance(ir.dst, IrVariable)
            dst_sym = qualified_symbols(ir.dst, self.scope)[-1]
            assert isinstance(dst_sym, Symbol)
            defstms = self.usedef.get_stms_defining(dst_sym)
            if len(defstms) != 1:
                return
            usestms = self.usedef.get_stms_using(dst_sym)
            for usestm in usestms:
                if self._can_inlining(usestm, ir):
                    usestm.replace(Temp(name=ir.dst.name), ir.src)

    class _Bin2Poly(IrTransformer):
        def visit_BinOp(self, ir):
            ir.left = self.visit(ir.left)
            ir.right = self.visit(ir.right)
            assert ir.left and ir.right
            if ir.op in ('Add', 'Mult'):
                values = []
                l = ir.left
                if isinstance(l, (BinOp, PolyOp)):
                    assert l.op == ir.op
                    values.extend(list(l.kids()))
                else:
                    values.append(l)
                r = ir.right
                if isinstance(r, (BinOp, PolyOp)):
                    assert l.op == ir.op
                    values.extend(list(r.kids()))
                else:
                    values.append(r)
                if len(values) > 2:
                    return PolyOp(op=ir.op, values=values)
            return ir

        def visit_PolyOp(self, ir):
            return ir

    class _Poly2Bin(IrTransformer):
        @staticmethod
        def _fold(poly):
            vars = []
            consts = []
            for e in poly.values:
                if isinstance(e, Const):
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
            return PolyOp(op=poly.op, values=vars + [Const(value=const_result)])

        def visit_PolyOp(self, ir):
            ir = self._fold(ir)
            assert len(ir.values) == 2
            return BinOp(op=ir.op, left=ir.values[0], right=ir.values[1])
