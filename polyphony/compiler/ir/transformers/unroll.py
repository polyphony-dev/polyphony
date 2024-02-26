from collections import defaultdict
from ..block import Block
from ..ir import *
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor, IRTransformer
from ..loop import Loop
from ..scope import Scope, NameReplacer
from ..types.type import Type
from ...common.common import fail
from ...common.errors import Errors
from logging import getLogger
logger = getLogger(__name__)


class LoopUnroller(object):
    def process(self, scope):
        self.scope = scope
        self.unrolled = False
        if self._unroll_loop_tree_leaf(scope.top_region()):
            # re-order blocks
            for blk in scope.traverse_blocks():
                blk.order = -1
                for stm in blk.stms:
                    assert stm.block is blk
            Block.set_order(scope.entry_block, 0)
            return True
        return False

    def _unroll_loop_tree_leaf(self, loop: Loop) -> bool:
        children: list[Loop] = sorted(self.scope.child_regions(loop), key=lambda c: c.head.order)
        for c in children.copy():
            assert isinstance(c, Loop)
            if self.scope.is_leaf_region(c):
                if not c.head.synth_params['unroll']:
                    continue
                factor = self._parse_factor(c.head.synth_params)
                if self._unroll(c, factor):
                    return True
                else:
                    #del c.head.synth_params['unroll']
                    for b in c.blocks():
                        del b.synth_params['unroll']
            else:
                if self._unroll_loop_tree_leaf(c):
                    return True
                if c.head.synth_params['unroll']:
                    fail(c.head.stms[-1], Errors.RULE_UNROLL_NESTED_LOOP)
        return False

    def _parse_factor(self, synth_params) -> int:
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

    def _unroll(self, loop: Loop, factor: int) -> bool:
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
        if isinstance(loop_max, CONST) and isinstance(loop_min, CONST):
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
        #unroll_trip = initial_trip // factor
        origin_body = loop.bodies[0]
        defsyms: set[Symbol] = self.scope.usedef.get_syms_defined_at(loop.head)
        origin_ivs: list[Symbol] = [sym for sym in defsyms if sym.is_induction()]
        new_ivs = self._new_ivs(factor, origin_ivs, is_full_unroll)
        if is_full_unroll:
            unroll_head, iv_updates, loop_cond = self._make_full_unroll_head(loop,
                                                                             new_ivs)
            sym_map: dict[str, Symbol] = {}
        else:
            unroll_head, iv_updates, lphis, sym_map = self._make_unroll_head(loop,
                                                                             loop_max,
                                                                             loop_step,
                                                                             factor,
                                                                             new_ivs)
        defsyms = self.scope.usedef.get_syms_defined_at(origin_body)
        unroll_blks = self._make_unrolling_blocks(origin_body,
                                                  defsyms,
                                                  new_ivs,
                                                  iv_updates,
                                                  sym_map,
                                                  factor,
                                                  unroll_head)
        if is_full_unroll:
            self._reconnect_full_unroll_blocks(loop, unroll_head, unroll_blks)
            self._replace_outer_uses(loop, new_ivs, factor, {})
            # emigrate unrolled blocks
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
            self._reconnect_unroll_blocks(loop, new_loop, unroll_head, unroll_blks, lphis, remain_start_blk)
            self.scope.append_sibling_region(loop, new_loop)
            if has_unroll_remain:
                assert loop.counter in new_ivs
                origin_lphis = {s.var.name:s for s in loop.head.stms if s.is_a(LPHI)}
                for sym, new_syms in new_ivs.items():
                    new_sym = new_syms[0]
                    lphi = origin_lphis[sym.name]
                    arg = TEMP(new_sym.name)
                    lphi.args[0] = arg
                assert remain_start_blk
                remain_start_blk.append_stm(EXPR(CONST(0)))  # guard from reduceblk
                remain_start_blk.append_stm(JUMP(loop.head))
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
        if jmp.is_a(JUMP):
            jmp.target = new
        elif jmp.is_a(CJUMP):
            if jmp.true is old:
                jmp.true = new
            else:
                assert jmp.false is old
                jmp.false = new
        elif jmp.is_a(MCJUMP):
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

        # loop_pred -> unroll_head
        loop_pred.replace_succ(loop.head, unroll_head)
        assert unroll_head.preds[0] is loop_pred
        assert not loop_pred.succs_loop

        # unroll_head
        assert len(unroll_head.succs) == 1 and unroll_head.succs[0] is first_blk
        assert len(first_blk.preds) == 1 and first_blk.preds[0] is unroll_head
        assert not unroll_head.succs_loop
        # no loop-back path
        unroll_head.preds = [loop_pred]
        unroll_head.preds_loop = []

        # last_blk -> loop_exit
        last_blk.succs = [loop_exit]
        last_blk.succs_loop = []

        # loop exit
        loop_exit.replace_pred(loop.head, last_blk)

        jmp = last_blk.stms[-1]
        assert jmp.is_a(JUMP)
        jmp.typ = ''
        jmp.target = loop_exit

    def _reconnect_unroll_blocks(self,
                                 loop: Loop,
                                 new_loop: Loop,
                                 unroll_head: Block,
                                 unroll_blks: list[Block],
                                 lphis: list[LPHI],
                                 remain_start_blk: Block|None):
        loop_pred = loop.head.preds[0]
        if remain_start_blk:
            loop_exit = remain_start_blk
            loop_exit.preds = [unroll_head]
        else:
            loop_exit = loop.head.succs[1]
            loop_exit.replace_pred(loop.head, unroll_head)
        first_blk = unroll_blks[0]
        last_blk = unroll_blks[-1]

        # loop_pred -> unroll_head
        loop_pred.replace_succ(loop.head, unroll_head)
        assert not loop_pred.succs_loop

        # unroll_head -> first_blk | loop_exit
        assert len(unroll_head.succs) == 1 and unroll_head.succs[0] is first_blk
        assert len(first_blk.preds) == 1 and first_blk.preds[0] is unroll_head
        assert not unroll_head.succs_loop

        unroll_head.succs.append(loop_exit)
        cjmp = unroll_head.stms[-1]
        assert cjmp.is_a(CJUMP)
        assert cjmp.false is None
        cjmp.false = loop_exit

        # add loop-back path from last_blk
        unroll_head.preds = [loop_pred, last_blk]
        unroll_head.preds_loop = [last_blk]

        # last_blk -> unroll_head
        last_blk.succs = [unroll_head]
        last_blk.succs_loop = [unroll_head]

        jmp = last_blk.stms[-1]
        assert jmp.is_a(JUMP)
        assert jmp.typ == 'L'
        jmp.target = unroll_head

    def _make_full_unroll_head(self,
                               loop: Loop,
                               new_ivs: dict[Symbol, list[Symbol]]) -> tuple[Block, dict[Symbol, list[Symbol]], Symbol]:
        unroll_head, stm_map = self._clone_block(loop.head, 'unroll_head')
        head_stms: list[IRStm] = []
        iv_updates: dict[Symbol, list[Symbol]] = {}
        # append initial move for each lphi
        #  i#2 = phi(init, i#3)  -> i#2_0 = 0
        #  x#2 = phi(x_init, x#3)  -> x#2_0 = x_init
        for _, stm in stm_map.items():
            if isinstance(stm, LPHI):
                assert len(stm.args) == 2
                orig_sym = qualified_symbols(stm.var, self.scope)[-1]
                assert isinstance(orig_sym, Symbol)
                new_sym_0 = new_ivs[orig_sym][0]
                dst = TEMP(new_sym_0.name, Ctx.STORE)
                src = stm.args[0]
                arg1_sym = qualified_symbols(stm.args[1], self.scope)[-1]
                assert isinstance(arg1_sym, Symbol)
                iv_updates[arg1_sym] = new_ivs[orig_sym]
                mv = MOVE(dst, src)
                head_stms.append(mv)
        orig_cjump_cond = unroll_head.stms[-2]
        assert orig_cjump_cond.is_a(MOVE) and orig_cjump_cond.src.is_a(RELOP)
        src = CONST(1)
        mv = MOVE(orig_cjump_cond.dst.clone(), src)
        head_stms.append(mv)
        orig_cjump = unroll_head.stms[-1]
        assert orig_cjump.is_a(CJUMP)
        jump = JUMP(None)
        jump.loc = orig_cjump.loc
        head_stms.append(jump)

        unroll_head.stms = []
        for stm in head_stms:
            unroll_head.append_stm(stm)
        dst_sym = qualified_symbols(orig_cjump_cond.dst, self.scope)[-1]
        assert isinstance(dst_sym, Symbol)
        return unroll_head, iv_updates, dst_sym

    def _make_unroll_head(self,
                          loop: Loop,
                          loop_max: IRExp,
                          loop_step: int,
                          factor: int,
                          new_ivs: dict[Symbol, list[Symbol]]) -> tuple[Block, dict[Symbol, list[Symbol]], list[LPHI], dict[str, Symbol]]:
        unroll_head, stm_map = self._clone_block(loop.head, 'unroll_head')
        head_stms: list[IRStm] = []
        iv_updates: dict[Symbol, list[Symbol]] = {}
        lphis: list[LPHI] = []
        sym_map: dict[str, Symbol] = {}
        # append modified lphi
        #  i#2 = phi(init, i#3)  -> i#2_0 = phi(0, i#2_n)
        #  x#2 = phi(x_init, x#3)  -> x#2_0 = phi(x_init, x#2_n)
        for _, stm in stm_map.items():
            if isinstance(stm, LPHI):
                assert len(stm.args) == 2
                orig_sym = qualified_symbols(stm.var, self.scope)[-1]
                assert isinstance(orig_sym, Symbol)
                new_sym_0 = new_ivs[orig_sym][0]
                new_sym_n = new_ivs[orig_sym][factor]
                stm.var.name = new_sym_0.name
                arg1_sym = qualified_symbols(stm.args[1], self.scope)[-1]
                assert isinstance(arg1_sym, Symbol)
                iv_updates[arg1_sym] = new_ivs[orig_sym]
                stm.args[1].name = new_sym_n.name
                head_stms.append(stm)
                lphis.append(stm)

        orig_cjump_cond = unroll_head.stms[-2]
        assert orig_cjump_cond.is_a(MOVE) and orig_cjump_cond.src.is_a(RELOP)
        orig_cjump = unroll_head.stms[-1]
        assert orig_cjump.is_a(CJUMP)
        new_loop_iv = new_ivs[loop.counter][0]
        tmp = self.scope.add_temp(typ=new_loop_iv.typ)
        mv = MOVE(TEMP(tmp.name),
                  BINOP('Add',
                        TEMP(new_loop_iv.name),
                        CONST((factor - 1) * loop_step)))
        head_stms.append(mv)
        cond_sym = self.scope.add_condition_sym()
        sym_map[orig_cjump_cond.dst.name] = cond_sym
        cond_stm = MOVE(TEMP(cond_sym.name), RELOP('Lt', TEMP(tmp.name), loop_max))
        cjump = CJUMP(TEMP(cond_sym.name), None, None, orig_cjump.loc)
        head_stms.append(cond_stm)
        head_stms.append(cjump)

        unroll_head.stms = []
        for stm in head_stms:
            unroll_head.append_stm(stm)
        return unroll_head, iv_updates, lphis, sym_map

    def _clone_block(self, blk: Block, nametag: str) -> tuple[Block, dict[IRStm, IRStm]]:
        stm_map: dict[IRStm, IRStm] = {}
        clone_blk = blk.clone(self.scope, stm_map, nametag)
        return clone_blk, stm_map

    def _find_unique_indexes(self, defsyms: set[Symbol], factor: int) -> dict[Symbol, int]:
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

    def _make_unrolling_blocks(self,
                               origin_block: Block,
                               defsyms: set[Symbol],
                               new_ivs: dict[Symbol, list[Symbol]],
                               iv_updates: dict[Symbol, list[Symbol]],
                               sym_map: dict[str, Symbol],
                               factor: int,
                               head: Block) -> list[Block]:
        pred_blk = head
        assert factor > 0
        new_blks: list[Block] = []
        defsym_indexes: dict[Symbol, int] = self._find_unique_indexes(defsyms, factor)
        for i in range(factor):
            new_blk, _ = self._clone_block(origin_block, 'unroll_body')
            new_blk.preds_loop = []
            new_blk.succs_loop = []
            ivreplacer = IVReplacer(self.scope, defsym_indexes, new_ivs, iv_updates, i)
            symreplacer = NameReplacer(sym_map)
            symreplacer.scope = self.scope
            for stm in new_blk.stms:
                ivreplacer.visit(stm)
                symreplacer.visit(stm)
            pred_blk.succs = [new_blk]
            jmp = pred_blk.stms[-1]
            jmp.typ = ''
            if jmp.is_a(CJUMP):
                jmp.true = new_blk
            else:
                assert jmp.is_a(JUMP)
                jmp.target = new_blk
            new_blk.preds = [pred_blk]
            pred_blk = new_blk
            new_blks.append(new_blk)
        return new_blks

    def _new_ivs(self,
                 factor: int,
                 ivs: list[Symbol],
                 is_full_unroll: bool) -> dict[Symbol, list[Symbol]]:
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

    def _replace_outer_uses(self,
                            loop: Loop,
                            new_ivs: dict[Symbol, list[Symbol]],
                            index: int,
                            sym_map: dict[str, Symbol]):
        for u in loop.outer_uses:
            usestms = self.scope.usedef.get_stms_using(u)
            for ustm in usestms:
                if u in new_ivs:
                    ustm.replace(u.name, new_ivs[u][index].name)
                if u.name in sym_map:
                    ustm.replace(u.name, sym_map[u.name].name)

    def _remove_loop_condition(self, cond):
        PHICondRemover(cond).process(self.scope)

    def _find_loop_range(self, loop) -> tuple[IRExp, IRExp, int] | None:
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

    def _find_loop_min(self, loop) -> IRExp:
        if loop.init.is_a(CONST):
            return loop.init
        elif loop.init.is_a(TEMP):
            return loop.init
        raise NotImplementedError('unsupported loop')

    def _find_loop_max(self, loop) -> IRExp:
        loop_cond_sym = loop.cond
        loop_cond_defs = self.scope.usedef.get_stms_defining(loop_cond_sym)
        assert len(loop_cond_defs) == 1
        loop_cond_stm = list(loop_cond_defs)[0]
        assert loop_cond_stm.is_a(MOVE)
        loop_cond_rhs = loop_cond_stm.src
        if loop_cond_rhs.is_a(RELOP):
            # We focus on simple increasing loops
            if loop_cond_rhs.op in ('Lt'):
                sym = qualified_symbols(loop_cond_rhs.left, self.scope)[-1]
                if sym is loop.counter:
                    may_max = loop_cond_rhs.right
                    if may_max.is_a(CONST):
                        return may_max
                    elif may_max.is_a(TEMP):
                        return may_max
        raise NotImplementedError('unsupported loop')

    def _find_loop_step(self, loop) -> int:
        loop_update = loop.update
        assert loop_update.is_a(TEMP)
        update_sym = qualified_symbols(loop_update, self.scope)[-1]
        update_defs = self.scope.usedef.get_stms_defining(update_sym)
        assert len(update_defs) == 1
        update_stm = list(update_defs)[0]
        assert update_stm.is_a(MOVE)
        update_rhs = update_stm.src
        if update_rhs.is_a(BINOP):
            if update_rhs.op == 'Add':
                sym = qualified_symbols(update_rhs.left, self.scope)[-1]
                if sym is loop.counter:
                    may_step = update_rhs.right
                    if may_step.is_a(CONST):
                        return may_step.value
                    else:
                        fail(update_stm, Errors.RULE_UNROLL_VARIABLE_STEP)
        fail(update_stm, Errors.RULE_UNROLL_UNKNOWN_STEP)


class IVReplacer(IRVisitor):
    def __init__(self, scope: Scope,
                 defsym_indexes: dict[Symbol, int],
                 new_ivs: dict[Symbol, list[Symbol]],
                 iv_updates: dict[Symbol, list[Symbol]],
                 idx: int):
        self.scope = scope
        self.defsym_indexes = defsym_indexes
        self.new_ivs = new_ivs
        self.iv_updates = iv_updates
        self.idx = idx

    def visit_TEMP(self, ir):
        sym = qualified_symbols(ir, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym not in self.defsym_indexes.keys() and sym not in self.new_ivs.keys():
            # this is loop invariant
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
        ir.name = new_sym.name


class PHICondRemover(IRTransformer):
    def __init__(self, sym):
        self.sym = sym

    def visit_UNOP(self, ir):
        sym = qualified_symbols(ir.exp, self.sym.scope)[-1]
        if ir.exp.is_a(TEMP) and sym is self.sym:
            return CONST(1)
        return ir

    def visit_TEMP(self, ir):
        sym = qualified_symbols(ir, self.sym.scope)[-1]
        if ir.ctx & Ctx.STORE == 0 and sym is self.sym:
            return CONST(1)
        return ir
