"""Constant optimization passes using new IR (ir.py).

ConstantOptBase: shared constant folding logic.
EarlyConstantOptNonSSA: pre-SSA constant optimization.
ConstantOpt: full constant optimization with worklist.
"""
from collections import defaultdict, deque
from typing import cast
from ..block import Block
from ..ir import (
    Const, Temp, Attr, UnOp, BinOp, RelOp, CondOp, PolyOp,
    Call, SysCall, New, MRef, MStore, Array,
    Move, CMove, Expr, CExpr, CJump, MCJump, Jump,
    IrExp, IrStm, IrVariable, IrNameExp, IrCallable, Phi, UPhi, LPhi,
    Ctx,
)
from ..irvisitor import IrVisitor, IrTransformer
from ..irhelper import (
    qualified_symbols, reduce_binop, reduce_relexp, irexp_type,
    eval_unop, eval_binop, eval_relop,
)
from ..symbol import Symbol
from ..types.type import Type
from ..analysis.dominator import DominatorTreeBuilder
from ..analysis.usedef import UseDefDetector, UseDefUpdater, UseDefTable
from .varreplacer import VarReplacer
from ...common.common import fail
from ...common.errors import Errors
from ...common.env import env
from ...common.utils import find_nth_item_index, remove_from_list
from logging import getLogger
logger = getLogger(__name__)


def _try_get_constant_new(qsym, scope):
    """Get constant value as Const, or None."""
    from ..irhelper import try_get_constant
    return try_get_constant(qsym, scope)


class ConstantOptBase(IrVisitor):
    usedef: UseDefTable

    def __init__(self):
        super().__init__()

    def process(self, scope):
        Block.set_order(scope.entry_block, 0)
        self.dtree = DominatorTreeBuilder(scope).process()
        super().process(scope)

    def visit_UnOp(self, ir):
        new_exp = self.visit(ir.exp)
        if isinstance(new_exp, Const):
            v = eval_unop(ir.op, new_exp.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return Const(value=v)
        if new_exp is not ir.exp:
            return ir.model_copy(update={'exp': new_exp})
        return ir

    def visit_BinOp(self, ir):
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if isinstance(new_left, Const) and isinstance(new_right, Const):
            v = eval_binop(ir.op, new_left.value, new_right.value)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return Const(value=v)
        if new_left is not ir.left or new_right is not ir.right:
            ir = ir.model_copy(update={'left': new_left, 'right': new_right})
        if isinstance(ir.left, Const) or isinstance(ir.right, Const):
            return reduce_binop(ir)
        return ir

    def visit_RelOp(self, ir):
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if new_left is not ir.left or new_right is not ir.right:
            ir = ir.model_copy(update={'left': new_left, 'right': new_right})
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
            assert isinstance(left_qsym[-1], Symbol) and isinstance(right_qsym[-1], Symbol)
            v = eval_relop(ir.op, left_qsym[-1].id, right_qsym[-1].id)
            if v is None:
                fail(self.current_stm, Errors.UNSUPPORTED_OPERATOR, [ir.op])
            return Const(value=v)
        return ir

    def visit_CondOp(self, ir):
        new_cond = self.visit(ir.cond)
        new_left = self.visit(ir.left)
        new_right = self.visit(ir.right)
        if isinstance(new_cond, Const):
            return new_left if new_cond.value else new_right
        if new_cond is not ir.cond or new_left is not ir.left or new_right is not ir.right:
            return ir.model_copy(update={'cond': new_cond, 'left': new_left, 'right': new_right})
        return ir

    def visit_Call(self, ir):
        new_args = tuple((name, self.visit(arg)) for name, arg in ir.args)
        args_changed = any(na is not oa for (_, na), (_, oa) in zip(new_args, ir.args))
        if args_changed:
            ir = ir.model_copy(update={'args': new_args})
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
        new_offset = self.visit(ir.offset)
        if new_offset is not ir.offset:
            return ir.model_copy(update={'offset': new_offset})
        return ir

    def visit_MStore(self, ir):
        new_offset = self.visit(ir.offset)
        new_exp = self.visit(ir.exp)
        if new_offset is not ir.offset or new_exp is not ir.exp:
            return ir.model_copy(update={'offset': new_offset, 'exp': new_exp})
        return ir

    def visit_Array(self, ir):
        new_repeat = self.visit(ir.repeat)
        new_items = [self.visit(item) for item in ir.items]
        repeat_changed = new_repeat is not ir.repeat
        items_changed = any(ni is not oi for ni, oi in zip(new_items, ir.items))
        if repeat_changed or items_changed:
            return ir.model_copy(update={'repeat': new_repeat, 'items': tuple(new_items)})
        return ir

    def visit_Temp(self, ir):
        return ir

    def visit_Attr(self, ir):
        return ir

    def visit_Expr(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            ir = ir.model_copy(update={'exp': new_exp})
        return ir

    def _replace_in_block(self, old_ir, new_ir):
        """Replace old_ir with new_ir in block.stms."""
        blk = self.scope.find_block(old_ir.block)
        blk.stms[blk.stms.index(old_ir)] = new_ir

    def visit_CJump(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            new_ir = ir.model_copy(update={'exp': new_exp})
            self._replace_in_block(ir, new_ir)
            ir = new_ir
        if isinstance(ir.exp, Const):
            self._process_unconditional_jump(ir, [])
        return None

    def visit_MCJump(self, ir):
        new_conds = tuple(self.visit(cond) for cond in ir.conds)
        if any(nc is not oc for nc, oc in zip(new_conds, ir.conds)):
            new_ir = ir.model_copy(update={'conds': new_conds})
            self._replace_in_block(ir, new_ir)
            ir = new_ir
        conds = [c.value for c in ir.conds if isinstance(c, Const)]
        if len(conds) == len(ir.conds) and conds.count(1) == 1:
            self._process_unconditional_jump(ir, [], conds)
        return None

    def visit_Jump(self, ir):
        pass

    def visit_Ret(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            return ir.model_copy(update={'exp': new_exp})
        return None

    def visit_Move(self, ir):
        new_src = self.visit(ir.src)
        if new_src is not ir.src:
            return ir.model_copy(update={'src': new_src})
        return None

    def visit_CExpr(self, ir):
        new_cond = self.visit(ir.cond)
        new_exp = self.visit(ir.exp)
        updates = {}
        if new_cond is not ir.cond:
            updates['cond'] = new_cond
        if new_exp is not ir.exp:
            updates['exp'] = new_exp
        if updates:
            return ir.model_copy(update=updates)
        return None

    def visit_CMove(self, ir):
        new_cond = self.visit(ir.cond)
        new_src = self.visit(ir.src)
        updates = {}
        if new_cond is not ir.cond:
            updates['cond'] = new_cond
        if new_src is not ir.src:
            updates['src'] = new_src
        if updates:
            return ir.model_copy(update=updates)
        return None

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
                        for pi, p in enumerate(phi.ps):
                            if isinstance(p, IrVariable):
                                v_sym = qualified_symbols(p, self.scope)[-1]
                                assert isinstance(v_sym, Symbol)
                                blks = self.usedef.get_blks_defining(v_sym)
                                if blk.bid in blks:
                                    new_phi = phi.model_copy(update={
                                        'args': phi.args[:pi] + phi.args[pi + 1:],
                                        'ps': phi.ps[:pi] + phi.ps[pi + 1:],
                                    })
                                    succ.replace_stm(phi, new_phi)
                                    break
                    lphis = succ.collect_stms([LPhi])
                    for lphi in lphis:
                        new_lphi = lphi.model_copy(update={
                            'args': lphi.args[:idx] + lphi.args[idx + 1:],
                            'ps': lphi.ps[:idx] + lphi.ps[idx + 1:],
                        })
                        succ.replace_stm(lphi, new_lphi)
                elif succ is not self.scope.entry_block:
                    self._remove_dominated_branch(succ, worklist)

    def _process_unconditional_jump(self, cjump, worklist, conds=None):
        blk = self.scope.find_block(cjump.block)
        if not blk.preds and self.scope.entry_block is not blk:
            return
        logger.debug('unconditional block {}'.format(blk.name))

        if isinstance(cjump, CJump):
            assert isinstance(cjump.exp, Const)
            true_idx = 0 if cjump.exp.value else 1
            target_bids = [cjump.true, cjump.false]
        else:
            assert conds is not None
            true_idx = conds.index(1)
            target_bids = cjump.targets[:]

        counts = defaultdict(int)
        targets_with_count = []
        for tgt_bid in target_bids:
            targets_with_count.append((tgt_bid, counts[tgt_bid]))
            counts[tgt_bid] += 1
        true_bid, true_i = targets_with_count[true_idx]
        true_blk = self.scope.find_block(true_bid)
        targets_with_count = targets_with_count[:true_idx] + targets_with_count[true_idx + 1:]
        for false_bid, blk_i in reversed(targets_with_count):
            false_blk = self.scope.find_block(false_bid)
            if false_blk.preds:
                idx = find_nth_item_index(false_blk.preds, blk, blk_i)
                assert idx >= 0
                false_blk.preds.pop(idx)
                phis = false_blk.collect_stms([Phi, LPhi])
                for phi in phis:
                    new_phi = phi.model_copy(update={
                        'args': phi.args[:idx] + phi.args[idx + 1:],
                        'ps': phi.ps[:idx] + phi.ps[idx + 1:],
                    })
                    false_blk.replace_stm(phi, new_phi)

            idx = find_nth_item_index(blk.succs, false_blk, blk_i)
            assert idx >= 0
            blk.succs.pop(idx)
            if self.scope.exit_block is false_blk and not false_blk.preds:
                self.scope.exit_block = blk
            preds = [p for p in false_blk.preds if p not in false_blk.preds_loop]
            if (not preds and
                    self.dtree.is_child(blk, false_blk)):
                self._remove_dominated_branch(false_blk, worklist)

        jump = Jump(target=true_bid, loc=cjump.loc, block=blk.bid)
        blk.replace_stm(cjump, jump)
        if cjump in worklist:
            worklist.remove(cjump)
        logger.debug(str(self.scope))


class EarlyConstantOptNonSSA(ConstantOptBase):
    def __init__(self):
        super().__init__()

    def process(self, scope):
        self.usedef = UseDefDetector().process(scope)
        super().process(scope)

    def visit_CJump(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            new_ir = ir.model_copy(update={'exp': new_exp})
            self._replace_in_block(ir, new_ir)
            ir = new_ir
        if isinstance(ir.exp, Const):
            self._process_unconditional_jump(ir, [])
            return None
        assert isinstance(ir.exp, IrVariable)
        exp_sym = qualified_symbols(ir.exp, self.scope)[-1]
        assert isinstance(exp_sym, Symbol)
        expdefs = self.usedef.get_stms_defining(exp_sym)
        assert len(expdefs) == 1
        expdef = list(expdefs)[0]
        if isinstance(expdef, Move) and isinstance(expdef.src, Const):
            new_ir = ir.model_copy(update={'exp': expdef.src})
            self._replace_in_block(ir, new_ir)
            self._process_unconditional_jump(new_ir, [])
        return None

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
    from ..irhelper import bits2int
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


class ConstantOpt(ConstantOptBase):
    def __init__(self):
        super().__init__()

    def process(self, scope, expr_type_index=None):
        if scope.is_class():
            return
        self.scope = scope
        self.dtree = DominatorTreeBuilder(scope).process()
        self.usedef = UseDefDetector().process(scope)
        self.udupdater = UseDefUpdater(scope, self.usedef)
        self.expr_type_index = expr_type_index if expr_type_index is not None else VarReplacer.build_expr_type_index()

        dead_stms = []
        self.worklist = deque()
        for blk in scope.traverse_blocks():
            self.worklist.extend(blk.stms)
        processed = set()
        while self.worklist:
            stm = self.worklist.popleft()
            stm_id = id(stm)
            if stm_id in processed:
                continue
            processed.add(stm_id)
            self.current_stm = stm
            result = self.visit(stm)
            if isinstance(result, IrStm) and result is not stm:
                blk = scope.find_block(stm.block)
                if stm in blk.stms:
                    blk.stms[blk.stms.index(stm)] = result
                    self.udupdater.update(stm, result)
                stm = result
            if isinstance(stm, (Phi, UPhi, LPhi)):
                # Skip stale phi: VarReplacer may have replaced this phi with a new
                # model_copy; if it's no longer in the block by identity, skip it.
                blk = scope.find_block(stm.block)
                if not any(s is stm for s in blk.stms):
                    continue
                new_ps = tuple(reduce_relexp(p) for p in stm.ps)
                if new_ps != stm.ps:
                    new_stm = stm.model_copy(update={'ps': new_ps})
                    blk.replace_stm(stm, new_stm)
                    self.udupdater.update(stm, new_stm)
                    stm = new_stm
                is_move = False
                for p in stm.ps:
                    if not isinstance(stm, LPhi) and isinstance(p, Const) and p.value and stm.ps.index(p) != (len(stm.ps) - 1):
                        is_move = True
                        idx = stm.ps.index(p)
                        mv = Move(dst=stm.var, src=stm.args[idx], block=stm.block)
                        blk = scope.find_block(stm.block)
                        blk.stms.insert(blk.stms.index(stm), mv)
                        self.udupdater.update(stm, mv)
                        self.worklist.append(mv)
                        dead_stms.append(stm)
                        break
                false_indices = [i for i, p in enumerate(stm.ps)
                                 if (isinstance(p, Const) and not p.value or
                                     isinstance(p, UnOp) and p.op == 'Not' and isinstance(p.exp, Const) and p.exp.value)]
                if not is_move and false_indices:
                    new_args = tuple(arg for i, arg in enumerate(stm.args) if i not in false_indices)
                    new_ps_clean = tuple(p for i, p in enumerate(stm.ps) if i not in false_indices)
                    blk = scope.find_block(stm.block)
                    new_stm = stm.model_copy(update={'args': new_args, 'ps': new_ps_clean})
                    blk.replace_stm(stm, new_stm)
                    self.udupdater.update(stm, new_stm)
                    stm = new_stm
                if not is_move and len(stm.args) == 1:
                    arg = stm.args[0]
                    blk = scope.find_block(stm.block)
                    mv = Move(dst=stm.var, src=arg, block=stm.block)
                    blk.stms.insert(blk.stms.index(stm), mv)
                    self.udupdater.update(stm, mv)
                    self.worklist.append(mv)
                    dead_stms.append(stm)
                elif len(stm.args) == 0:
                    dead_stms.append(stm)
            elif isinstance(stm, (CMove, CExpr)):
                new_cond = reduce_relexp(stm.cond)
                if new_cond is not stm.cond:
                    blk = scope.find_block(stm.block)
                    new_stm_copy = stm.model_copy(update={'cond': new_cond})
                    blk.stms[blk.stms.index(stm)] = new_stm_copy
                    stm = new_stm_copy
                if isinstance(stm.cond, Const):
                    if stm.cond.value:
                        blk = scope.find_block(stm.block)
                        if isinstance(stm, CMove):
                            new_stm = Move(dst=stm.dst, src=stm.src, block=stm.block)
                        else:
                            new_stm = Expr(exp=stm.exp, block=stm.block)
                        self.udupdater.update(stm, new_stm)
                        blk.stms.insert(blk.stms.index(stm), new_stm)
                    dead_stms.append(stm)
            elif (isinstance(stm, Move)
                    and isinstance(stm.src, Const)
                    and isinstance(stm.dst, Temp)
                    and isinstance((dst_sym := qualified_symbols(stm.dst, self.scope)[-1]), Symbol)
                    and not dst_sym.is_return()):
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
                replaces = VarReplacer.replace_uses(scope, stm.dst, src, self.usedef, self.expr_type_index)
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
                assert isinstance(stm, Move)
                dst_load = stm.dst.model_copy(update={'ctx': Ctx.LOAD})
                dst_store = stm.dst
                blk = scope.find_block(stm.block)
                try:
                    stm_idx = blk.stms.index(stm)
                except ValueError:
                    continue  # stm no longer in block; skip propagation
                found_new_def = False
                i = stm_idx + 1
                while i < len(blk.stms):
                    next_stm = blk.stms[i]
                    use_vars = self.usedef.get_vars_used_at(next_stm)
                    replaced_stm = next_stm
                    for v in use_vars:
                        if dst_load == v:
                            # Replace use in next_stm; capture new stm for def-check and worklist update
                            replacer = VarReplacer(scope, dst_load, stm.src, self.usedef)
                            new_next_stm = replacer.visit(next_stm)
                            if new_next_stm is not None and new_next_stm is not next_stm:
                                replaced_stm = new_next_stm
                                try:
                                    wl_idx = self.worklist.index(next_stm)
                                    self.worklist[wl_idx] = new_next_stm
                                except ValueError:
                                    self.worklist.append(new_next_stm)
                            break
                    def_vars = self.usedef.get_vars_defined_at(replaced_stm)
                    for v in def_vars:
                        if dst_store == v:
                            found_new_def = True
                            break
                    if found_new_def:
                        break
                    i += 1
            elif (isinstance(stm, Move)
                    and isinstance(stm.src, Array)
                    and isinstance(stm.src.repeat, Const)):
                src = stm.src
                dst_sym = qualified_symbols(cast(IrNameExp, stm.dst), self.scope)[-1]
                assert isinstance(dst_sym, Symbol)
                array_t = dst_sym.typ
                assert array_t.is_seq()
                if array_t.length == Type.ANY_LENGTH:
                    dst_sym.typ = dst_sym.typ.clone(length=len(src.items) * src.repeat.value)
        for stm in dead_stms:
            stm_blk = scope.find_block(stm.block)
            if stm in stm_blk.stms:
                stm_blk.stms.remove(stm)

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
        clos_usedef = UseDefDetector().process(closure)
        VarReplacer.replace_uses(closure, Temp(name=target.name), src, clos_usedef)

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
                    objscope = env.origin_registry.scope_origin_of(objscope)
                    if objscope is not None and objscope.parent is not None:
                        classsym = objscope.parent.find_sym(objscope.base_name)
                c = _try_get_constant_new((classsym, attr), self.scope)
                if c:
                    return c
        return ir

    def visit_Phi(self, ir):
        ir_blk = self.scope.find_block(ir.block)
        if not ir_blk.is_hyperblock and len(ir_blk.preds) != len(ir.args):
            new_args = ir.args
            new_ps = ir.ps
            for arg, blk in zip(ir.args, ir_blk.preds):
                if blk and blk is not self.scope.entry_block and not blk.preds:
                    idx = new_args.index(arg)
                    new_args = new_args[:idx] + new_args[idx + 1:]
                    new_ps = new_ps[:idx] + new_ps[idx + 1:]
            if new_args != ir.args:
                return ir.model_copy(update={'args': new_args, 'ps': new_ps})
        return ir

    def visit_CJump(self, ir):
        new_exp = self.visit(ir.exp)
        if new_exp is not ir.exp:
            new_ir = ir.model_copy(update={'exp': new_exp})
            self._replace_in_block(ir, new_ir)
            ir = new_ir
        if isinstance(ir.exp, Const):
            self._process_unconditional_jump(ir, self.worklist)
        return None

    def visit_MCJump(self, ir):
        new_conds = tuple(self.visit(cond) for cond in ir.conds)
        if any(nc is not oc for nc, oc in zip(new_conds, ir.conds)):
            new_ir = ir.model_copy(update={'conds': new_conds})
            self._replace_in_block(ir, new_ir)
            ir = new_ir
        conds = [c.value for c in ir.conds if isinstance(c, Const)]
        if len(conds) == len(ir.conds) and conds.count(1) == 1:
            self._process_unconditional_jump(ir, self.worklist, conds)
        return None
        return ir


class StaticConstOpt(ConstantOptBase):
    """Propagate static constants across scopes using new IR."""

    def __init__(self):
        self.constant_table: dict[Symbol, Const] = {}
        self.constant_array_table: dict[Symbol, Array] = {}

    def process_scopes(self, scopes):
        stms = []
        stm2scope = {}
        stm2blk = {}
        dtrees = {}
        for s in scopes:
            for blk in s.traverse_blocks():
                for stm in blk.stms:
                    stm2scope[id(stm)] = s
                    stm2blk[id(stm)] = blk
                stms.extend(blk.stms)
            Block.set_order(s.entry_block, 0)
            dtree = DominatorTreeBuilder(s).process()
            dtrees[s] = dtree
        # Sort by line number (matches old behavior)
        stms = sorted(stms, key=lambda s: s.loc.lineno)
        for stm in stms:
            self.current_stm = stm
            stm_scope = stm2scope[id(stm)]
            self.scope = stm_scope
            self.dtree = dtrees[stm_scope]
            result = self.visit(stm)
            if isinstance(result, IrStm) and result is not stm:
                blk = stm2blk[id(stm)]
                blk.stms[blk.stms.index(stm)] = result
        for sym, c in sorted(self.constant_table.items(), key=lambda x: x[0].name):
            sym.scope.constants[sym] = c
            origin_scope = env.origin_registry.scope_origin_of(sym.scope)
            if origin_scope:
                if sym.name in origin_scope.symbols:
                    origin_scope.constants[origin_scope.symbols[sym.name]] = c
        for sym, c in sorted(self.constant_array_table.items(), key=lambda x: x[0].name):
            sym.scope.constants[sym] = c
            origin_scope = env.origin_registry.scope_origin_of(sym.scope)
            if origin_scope:
                if sym.name in origin_scope.symbols:
                    origin_scope.constants[origin_scope.symbols[sym.name]] = c



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
        new_offset = self.visit(ir.offset)
        if new_offset is not ir.offset:
            ir = ir.model_copy(update={'offset': new_offset})
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
        if src is not ir.src:
            ir = ir.model_copy(update={'src': src})
        return ir


class PolyadConstantFolding(object):
    """Convert binary ops to poliad ops and fold constants, using new IR."""

    def process(self, scope):
        self._BinInlining().process(scope)
        self._Bin2Poly().process(scope)
        self._Poly2Bin().process(scope)

    class _BinInlining(IrTransformer):
        def process(self, scope):
            from ..analysis.usedef import UseDefDetector, UseDefUpdater
            self.usedef = UseDefDetector().process(scope)
            self.udupdater = UseDefUpdater(scope, self.usedef)
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
                    new_usestm = usestm.subst(Temp(name=ir.dst.name), ir.src)
                    if new_usestm is not usestm:
                        self.udupdater.update(usestm, new_usestm)
                        self.scope.find_block(usestm.block).replace_stm(usestm, new_usestm)

    class _Bin2Poly(IrTransformer):
        def visit_BinOp(self, ir):
            new_left = self.visit(ir.left)
            new_right = self.visit(ir.right)
            if new_left is not ir.left or new_right is not ir.right:
                ir = ir.model_copy(update={'left': new_left, 'right': new_right})
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
                    return PolyOp(op=ir.op, values=tuple(values))
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
            const_result = 0
            if poly.op == 'Add':
                const_result = 0
                for c in consts:
                    const_result += c.value
            elif poly.op == 'Mult':
                const_result = 1
                for c in consts:
                    const_result *= c.value
            return PolyOp(op=poly.op, values=tuple(vars + [Const(value=const_result)]))

        def visit_PolyOp(self, ir):
            ir = self._fold(ir)
            assert len(ir.values) == 2
            return BinOp(op=ir.op, left=ir.values[0], right=ir.values[1])
