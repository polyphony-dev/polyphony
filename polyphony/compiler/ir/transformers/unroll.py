"""Loop unrolling using new IR (ir.py).

Contains:
- LoopUnroller: main unroller
- IVReplacer: induction variable replacement
- PHICondRemover: removes PHI conditions after unrolling
"""
from collections import defaultdict
from ..block import Block
from ..ir import (
    Ctx, Const, Temp, BinOp, RelOp, Move, Expr, Jump, CJump, MCJump,
    LPhi, IrStm, IrExp,
)
from ..ir import Const as OldCONST, Temp as OldTEMP
from ..irvisitor import IrVisitor, IrTransformer
from ..irhelper import qualified_symbols
from ..loop import Loop
from ..scope import Scope, NameReplacer
from ..symbol import Symbol
from ..types.type import Type
from ..analysis.usedef import UseDefDetector
from ...common.common import fail
from ...common.errors import Errors
from logging import getLogger
logger = getLogger(__name__)


def _clone_ir_block(blk, scope, nametag=None):
    """Clone a block and its stms.

    Returns (new_block, stm_map) where stm_map maps old stms to new stms.
    """
    if nametag:
        b = Block(scope, nametag)
    else:
        b = Block(scope, blk.nametag)
    stm_map = {}
    for stm in blk.stms:
        new_stm = stm.model_copy(deep=True)
        object.__setattr__(new_stm, 'block', b)
        b.stms.append(new_stm)
        stm_map[stm] = new_stm
    b.order = blk.order
    b.succs = list(blk.succs)
    b.succs_loop = list(blk.succs_loop)
    b.preds = list(blk.preds)
    b.preds_loop = list(blk.preds_loop)
    b.synth_params = blk.synth_params.copy()
    b.is_hyperblock = blk.is_hyperblock
    if blk.path_exp:
        b.path_exp = blk.path_exp.model_copy(deep=True)
    return b, stm_map


class LoopUnroller(object):
    def process(self, scope):
        self.scope = scope
        self.usedef = UseDefDetector().process(scope)
        self.unrolled = False
        if self._unroll_loop_tree_leaf(scope.top_region()):
            # Re-order blocks
            for blk in scope.traverse_blocks():
                blk.order = -1
                for stm in blk.stms:
                    assert stm.block is blk
            logger.debug(f'Block.set_order start for {scope}')
            Block.set_order(scope.entry_block, 0)
            logger.debug(f'Block.set_order done for {scope}')
            return True
        return False

    def _unroll_loop_tree_leaf(self, loop):
        children = sorted(self.scope.child_regions(loop), key=lambda c: c.head.order)
        for c in children.copy():
            assert isinstance(c, Loop)
            if self.scope.is_leaf_region(c):
                if not c.head.synth_params['unroll']:
                    continue
                factor = self._parse_factor(c.head.synth_params)
                if self._unroll(c, factor):
                    return True
                else:
                    for b in c.blocks():
                        del b.synth_params['unroll']
            else:
                if self._unroll_loop_tree_leaf(c):
                    return True
                if c.head.synth_params['unroll']:
                    fail(c.head.stms[-1], Errors.RULE_UNROLL_NESTED_LOOP)
        return False

    def _parse_factor(self, synth_params):
        if isinstance(synth_params['unroll'], str):
            if synth_params['unroll'] == 'full':
                factor = -1
            else:
                try:
                    factor = int(synth_params['unroll'])
                except:
                    factor = 0
        elif isinstance(synth_params['unroll'], int):
            factor = synth_params['unroll']
        else:
            assert False, 'Invalid unroll parameter'
        return factor

    def _unroll(self, loop, factor):
        if factor == 1:
            return False
        assert self.scope.is_leaf_region(loop)
        assert loop.counter
        assert loop.init
        assert loop.update
        assert loop.cond
        if len(loop.bodies) > 1:
            for b in loop.bodies:
                if len(b.succs) > 1:
                    fail(loop.head.stms[-1],
                         Errors.RULE_UNROLL_CONTROL_BRANCH)
        assert len(loop.bodies) == 1
        ret = self._find_loop_range(loop)
        if not ret:
            fail(loop.head.stms[-1],
                 Errors.RULE_UNROLL_UNFIXED_LOOP)
        assert isinstance(ret, tuple)
        loop_min, loop_max, loop_step = ret
        if isinstance(loop_max, Const) and isinstance(loop_min, Const):
            initial_trip = (((loop_max.value - 1) + loop_step) - loop_min.value) // loop_step
            if initial_trip < 1:
                return False
            if factor == -1 or factor >= loop_max.value:
                factor = initial_trip
            has_unroll_remain = True if initial_trip % factor else False
            is_full_unroll = factor == initial_trip
        else:
            initial_trip = -1
            if factor == -1:
                fail(loop.head.stms[-1],
                     Errors.RULE_UNROLL_UNFIXED_LOOP)
            has_unroll_remain = True
            is_full_unroll = False

        origin_body = loop.bodies[0]
        defsyms = self.usedef.get_syms_defined_at(loop.head)
        origin_ivs = [sym for sym in defsyms if sym.is_induction()]
        new_ivs = self._new_ivs(factor, origin_ivs, is_full_unroll)
        if is_full_unroll:
            unroll_head, iv_updates, loop_cond = self._make_full_unroll_head(
                loop, new_ivs)
            sym_map = {}
        else:
            unroll_head, iv_updates, lphis, sym_map = self._make_unroll_head(
                loop, loop_max, loop_step, factor, new_ivs)
        defsyms = self.usedef.get_syms_defined_at(origin_body)
        unroll_blks = self._make_unrolling_blocks(
            origin_body, defsyms, new_ivs, iv_updates, sym_map, factor, unroll_head)
        if is_full_unroll:
            self._reconnect_full_unroll_blocks(loop, unroll_head, unroll_blks)
            self._replace_outer_uses(loop, new_ivs, factor, {})
            parent = self.scope.parent_region(loop)
            for b in [unroll_head] + unroll_blks:
                parent.append_body(b)
            self.scope.remove_region(loop)
            self._remove_loop_condition(loop_cond)
            for blk in [unroll_head] + unroll_blks:
                blk.synth_params = unroll_head.preds[0].synth_params.copy()
        else:
            if has_unroll_remain:
                remain_start_blk = Block(self.scope)
            else:
                remain_start_blk = None
            new_loop = Loop(unroll_head, unroll_blks, [unroll_head] + unroll_blks)
            self._reconnect_unroll_blocks(
                loop, new_loop, unroll_head, unroll_blks, lphis, remain_start_blk)
            self.scope.append_sibling_region(loop, new_loop)
            if has_unroll_remain:
                assert loop.counter in new_ivs
                origin_lphis = {s.var.name: s for s in loop.head.stms if isinstance(s, LPhi)}
                for sym, new_syms in new_ivs.items():
                    new_sym = new_syms[0]
                    lphi = origin_lphis[sym.name]
                    arg = Temp(name=new_sym.name)
                    lphi.args[0] = arg
                assert remain_start_blk
                guard = Expr(exp=Const(value=0))
                object.__setattr__(guard, 'block', remain_start_blk)
                remain_start_blk.stms.append(guard)
                jmp = Jump(target=loop.head)
                object.__setattr__(jmp, 'block', remain_start_blk)
                remain_start_blk.stms.append(jmp)
                remain_start_blk.succs = [loop.head]
                loop.head.preds[0] = remain_start_blk
                del loop.head.synth_params['unroll']
                parent = self.scope.parent_region(loop)
                parent.append_body(remain_start_blk)
            else:
                self.scope.remove_region(loop)
                self._replace_outer_uses(loop, new_ivs, 0, sym_map)
            for blk in [unroll_head] + unroll_blks:
                del blk.synth_params['unroll']
        return True

    def _replace_jump_target(self, block, old, new):
        jmp = block.stms[-1]
        if isinstance(jmp, Jump):
            object.__setattr__(jmp, 'target', new)
        elif isinstance(jmp, CJump):
            if jmp.true is old:
                object.__setattr__(jmp, 'true', new)
            else:
                assert jmp.false is old
                object.__setattr__(jmp, 'false', new)
        elif isinstance(jmp, MCJump):
            for i, t in enumerate(jmp.targets):
                if t is old:
                    jmp.targets[i] = new
        else:
            assert False

    def _reconnect_full_unroll_blocks(self, loop, unroll_head, unroll_blks):
        loop_pred = loop.head.preds[0]
        loop_exit = loop.head.succs[1]
        first_blk = unroll_blks[0]
        last_blk = unroll_blks[-1]

        loop_pred.replace_succ(loop.head, unroll_head)
        assert unroll_head.preds[0] is loop_pred
        assert not loop_pred.succs_loop

        assert len(unroll_head.succs) == 1 and unroll_head.succs[0] is first_blk
        assert len(first_blk.preds) == 1 and first_blk.preds[0] is unroll_head
        assert not unroll_head.succs_loop
        unroll_head.preds = [loop_pred]
        unroll_head.preds_loop = []

        last_blk.succs = [loop_exit]
        last_blk.succs_loop = []

        loop_exit.replace_pred(loop.head, last_blk)

        jmp = last_blk.stms[-1]
        assert isinstance(jmp, Jump)
        object.__setattr__(jmp, 'typ', '')
        object.__setattr__(jmp, 'target', loop_exit)

    def _reconnect_unroll_blocks(self, loop, new_loop, unroll_head, unroll_blks, lphis, remain_start_blk):
        loop_pred = loop.head.preds[0]
        if remain_start_blk:
            loop_exit = remain_start_blk
            loop_exit.preds = [unroll_head]
        else:
            loop_exit = loop.head.succs[1]
            loop_exit.replace_pred(loop.head, unroll_head)
        first_blk = unroll_blks[0]
        last_blk = unroll_blks[-1]

        loop_pred.replace_succ(loop.head, unroll_head)
        assert not loop_pred.succs_loop

        assert len(unroll_head.succs) == 1 and unroll_head.succs[0] is first_blk
        assert len(first_blk.preds) == 1 and first_blk.preds[0] is unroll_head
        assert not unroll_head.succs_loop

        unroll_head.succs.append(loop_exit)
        cjmp = unroll_head.stms[-1]
        assert isinstance(cjmp, CJump)
        assert cjmp.false is None
        object.__setattr__(cjmp, 'false', loop_exit)

        unroll_head.preds = [loop_pred, last_blk]
        unroll_head.preds_loop = [last_blk]

        last_blk.succs = [unroll_head]
        last_blk.succs_loop = [unroll_head]

        jmp = last_blk.stms[-1]
        assert isinstance(jmp, Jump)
        assert jmp.typ == 'L'
        object.__setattr__(jmp, 'target', unroll_head)

    def _make_full_unroll_head(self, loop, new_ivs):
        unroll_head, stm_map = _clone_ir_block(loop.head, self.scope, 'unroll_head')
        head_stms = []
        iv_updates = {}
        # Append initial move for each lphi
        for _, stm in stm_map.items():
            if isinstance(stm, LPhi):
                assert len(stm.args) == 2
                orig_sym = qualified_symbols(stm.var, self.scope)[-1]
                assert isinstance(orig_sym, Symbol)
                new_sym_0 = new_ivs[orig_sym][0]
                dst = Temp(name=new_sym_0.name, ctx=Ctx.STORE)
                src = stm.args[0]
                arg1_sym = qualified_symbols(stm.args[1], self.scope)[-1]
                assert isinstance(arg1_sym, Symbol)
                iv_updates[arg1_sym] = new_ivs[orig_sym]
                mv = Move(dst=dst, src=src)
                head_stms.append(mv)
        orig_cjump_cond = unroll_head.stms[-2]
        assert isinstance(orig_cjump_cond, Move) and isinstance(orig_cjump_cond.src, RelOp)
        src = Const(value=1)
        mv = Move(dst=orig_cjump_cond.dst.model_copy(deep=True), src=src)
        head_stms.append(mv)
        orig_cjump = unroll_head.stms[-1]
        assert isinstance(orig_cjump, CJump)
        jump = Jump(target=None)
        object.__setattr__(jump, 'loc', orig_cjump.loc)
        head_stms.append(jump)

        unroll_head.stms = []
        for stm in head_stms:
            object.__setattr__(stm, 'block', unroll_head)
            unroll_head.stms.append(stm)
        dst_sym = qualified_symbols(orig_cjump_cond.dst, self.scope)[-1]
        assert isinstance(dst_sym, Symbol)
        return unroll_head, iv_updates, dst_sym

    def _make_unroll_head(self, loop, loop_max, loop_step, factor, new_ivs):
        unroll_head, stm_map = _clone_ir_block(loop.head, self.scope, 'unroll_head')
        head_stms = []
        iv_updates = {}
        lphis = []
        sym_map = {}
        for _, stm in stm_map.items():
            if isinstance(stm, LPhi):
                assert len(stm.args) == 2
                orig_sym = qualified_symbols(stm.var, self.scope)[-1]
                assert isinstance(orig_sym, Symbol)
                new_sym_0 = new_ivs[orig_sym][0]
                new_sym_n = new_ivs[orig_sym][factor]
                object.__setattr__(stm.var, 'name', new_sym_0.name)
                arg1_sym = qualified_symbols(stm.args[1], self.scope)[-1]
                assert isinstance(arg1_sym, Symbol)
                iv_updates[arg1_sym] = new_ivs[orig_sym]
                object.__setattr__(stm.args[1], 'name', new_sym_n.name)
                head_stms.append(stm)
                lphis.append(stm)

        orig_cjump_cond = unroll_head.stms[-2]
        assert isinstance(orig_cjump_cond, Move) and isinstance(orig_cjump_cond.src, RelOp)
        orig_cjump = unroll_head.stms[-1]
        assert isinstance(orig_cjump, CJump)
        new_loop_iv = new_ivs[loop.counter][0]
        tmp = self.scope.add_temp(typ=new_loop_iv.typ)
        mv = Move(
            dst=Temp(name=tmp.name, ctx=Ctx.STORE),
            src=BinOp(
                op='Add',
                left=Temp(name=new_loop_iv.name),
                right=Const(value=(factor - 1) * loop_step)))
        head_stms.append(mv)
        cond_sym = self.scope.add_condition_sym()
        sym_map[orig_cjump_cond.dst.name] = cond_sym
        cond_stm = Move(
            dst=Temp(name=cond_sym.name, ctx=Ctx.STORE),
            src=RelOp(op='Lt', left=Temp(name=tmp.name), right=loop_max.model_copy(deep=True)))
        cjump = CJump(exp=Temp(name=cond_sym.name), true=None, false=None, loc=orig_cjump.loc)
        head_stms.append(cond_stm)
        head_stms.append(cjump)

        unroll_head.stms = []
        for stm in head_stms:
            object.__setattr__(stm, 'block', unroll_head)
            unroll_head.stms.append(stm)
        return unroll_head, iv_updates, lphis, sym_map

    def _find_unique_indexes(self, defsyms, factor):
        results = {}
        for sym in defsyms:
            index = 0
            while True:
                if all([not self.scope.has_sym(f'{sym.name}_{index + i}') for i in range(factor)]):
                    break
                else:
                    index += 1
            results[sym] = index
        return results

    def _make_unrolling_blocks(self, origin_block, defsyms, new_ivs, iv_updates, sym_map, factor, head):
        pred_blk = head
        assert factor > 0
        new_blks = []
        defsym_indexes = self._find_unique_indexes(defsyms, factor)
        for i in range(factor):
            new_blk, _ = _clone_ir_block(origin_block, self.scope, 'unroll_body')
            new_blk.preds_loop = []
            new_blk.succs_loop = []
            ivreplacer = IVReplacer(self.scope, defsym_indexes, new_ivs, iv_updates, i)
            symreplacer = _NewNameReplacer(self.scope, sym_map)
            for stm in new_blk.stms:
                ivreplacer.visit(stm)
                symreplacer.visit(stm)
            pred_blk.succs = [new_blk]
            jmp = pred_blk.stms[-1]
            if isinstance(jmp, Jump):
                object.__setattr__(jmp, 'typ', '')
                object.__setattr__(jmp, 'target', new_blk)
            elif isinstance(jmp, CJump):
                object.__setattr__(jmp, 'true', new_blk)
            else:
                assert False
            new_blk.preds = [pred_blk]
            pred_blk = new_blk
            new_blks.append(new_blk)
        return new_blks

    def _new_ivs(self, factor, ivs, is_full_unroll):
        new_iv_map = defaultdict(list)
        for i in range(factor + 1):
            for iv in ivs:
                new_name = '{}_{}'.format(iv.name, i)
                assert not self.scope.has_sym(new_name)
                new_iv = self.scope.inherit_sym(iv, new_name)
                new_iv_map[iv].append(new_iv)
                if i != 0 or is_full_unroll:
                    new_iv.del_tag('induction')
        return new_iv_map

    def _replace_outer_uses(self, loop, new_ivs, index, sym_map):
        for u in loop.outer_uses:
            usestms = self.usedef.get_stms_using(u)
            for ustm in usestms:
                if u in new_ivs:
                    ustm.replace(u.name, new_ivs[u][index].name)
                if u.name in sym_map:
                    ustm.replace(u.name, sym_map[u.name].name)

    def _remove_loop_condition(self, cond):
        PHICondRemover(cond).process(self.scope)

    def _find_loop_range(self, loop):
        loop_min = self._find_loop_min(loop)
        if loop_min is None:
            return None
        loop_max = self._find_loop_max(loop)
        if loop_max is None:
            return None
        loop_step = self._find_loop_step(loop)
        if not isinstance(loop_step, int):
            return None
        return (loop_min, loop_max, loop_step)

    def _ensure_new_ir(self, ir):
        """Convert old IR to new IR if needed."""
        if isinstance(ir, (Const, Temp)):
            return ir
        if isinstance(ir, (OldCONST, OldTEMP)):
            return ir
        return ir

    def _find_loop_min(self, loop):
        init = self._ensure_new_ir(loop.init)
        if isinstance(init, Const):
            return init
        elif isinstance(init, Temp):
            return init
        raise NotImplementedError('unsupported loop')

    def _find_loop_max(self, loop):
        loop_cond_sym = loop.cond
        loop_cond_defs = self.usedef.get_stms_defining(loop_cond_sym)
        assert len(loop_cond_defs) == 1
        loop_cond_stm = list(loop_cond_defs)[0]
        assert isinstance(loop_cond_stm, Move)
        loop_cond_rhs = loop_cond_stm.src
        if isinstance(loop_cond_rhs, RelOp):
            if loop_cond_rhs.op in ('Lt',):
                sym = qualified_symbols(loop_cond_rhs.left, self.scope)[-1]
                if sym is loop.counter:
                    may_max = loop_cond_rhs.right
                    if isinstance(may_max, Const):
                        return may_max
                    elif isinstance(may_max, Temp):
                        return may_max
        raise NotImplementedError('unsupported loop')

    def _find_loop_step(self, loop):
        loop_update = self._ensure_new_ir(loop.update)
        assert isinstance(loop_update, Temp)
        update_sym = qualified_symbols(loop_update, self.scope)[-1]
        update_defs = self.usedef.get_stms_defining(update_sym)
        assert len(update_defs) == 1
        update_stm = list(update_defs)[0]
        assert isinstance(update_stm, Move)
        update_rhs = update_stm.src
        if isinstance(update_rhs, BinOp):
            if update_rhs.op == 'Add':
                sym = qualified_symbols(update_rhs.left, self.scope)[-1]
                if sym is loop.counter:
                    may_step = update_rhs.right
                    if isinstance(may_step, Const):
                        return may_step.value
                    else:
                        fail(update_stm, Errors.RULE_UNROLL_VARIABLE_STEP)
        fail(update_stm, Errors.RULE_UNROLL_UNKNOWN_STEP)


class IVReplacer(IrVisitor):
    """Replace induction variables in unrolled loop bodies."""
    def __init__(self, scope, defsym_indexes, new_ivs, iv_updates, idx):
        self.scope = scope
        self.defsym_indexes = defsym_indexes
        self.new_ivs = new_ivs
        self.iv_updates = iv_updates
        self.idx = idx

    def process(self, scope):
        # Override: don't iterate blocks, visitor is called per-stm
        pass

    def visit_Temp(self, ir):
        sym = qualified_symbols(ir, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym not in self.defsym_indexes.keys() and sym not in self.new_ivs.keys():
            return
        if not sym.typ.is_scalar():
            return
        if sym.is_induction():
            assert sym in self.new_ivs.keys()
            new_sym = self.new_ivs[sym][self.idx]
        elif sym in self.iv_updates:
            new_sym = self.iv_updates[sym][self.idx + 1]
        else:
            new_name = '{}_{}'.format(sym.name, self.defsym_indexes[sym] + self.idx)
            new_sym = self.scope.inherit_sym(sym, new_name)
        object.__setattr__(ir, 'name', new_sym.name)


class _NewNameReplacer(IrVisitor):
    """Replace variable names from a sym_map (new IR version)."""
    def __init__(self, scope, sym_map):
        self.scope = scope
        self.sym_map = sym_map

    def process(self, scope):
        pass

    def visit_Temp(self, ir):
        if ir.name in self.sym_map:
            object.__setattr__(ir, 'name', self.sym_map[ir.name].name)


class PHICondRemover(IrTransformer):
    """Remove PHI conditions after full unroll by replacing cond with Const(1)."""
    def __init__(self, sym):
        self.sym = sym

    def visit_UnOp(self, ir):
        sym = qualified_symbols(ir.exp, self.sym.scope)[-1]
        if isinstance(ir.exp, Temp) and sym is self.sym:
            return Const(value=1)
        return ir

    def visit_Temp(self, ir):
        sym = qualified_symbols(ir, self.sym.scope)[-1]
        if ir.ctx != Ctx.STORE and sym is self.sym:
            return Const(value=1)
        return ir
