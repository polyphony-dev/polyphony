from collections import defaultdict
from .block import Block, CompositBlock
from .common import fail
from .errors import Errors
from .ir import *
from .irvisitor import IRVisitor
from .loopdetector import LoopInfoSetter, LoopDependencyDetector
from . import utils
from logging import getLogger
logger = getLogger(__name__)


class LoopUnroller(object):
    def process(self, scope):
        self.scope = scope
        self.unrolled = False
        if self._unroll_loop_tree_leaf(scope.entry_block):
            # re-order blocks
            for blk in scope.traverse_blocks():
                blk.order = -1
                for stm in blk.stms:
                    assert stm.block is blk
            Block.set_order(scope.entry_block, 0)
            return True
        return False

    def _unroll_loop_tree_leaf(self, blk):
        children = self.scope.loop_nest_tree.get_children_of(blk)
        for c in children.copy():
            if self.scope.loop_nest_tree.is_leaf(c):
                if not c.synth_params['unroll']:
                    continue
                factor = self._parse_factor(c.synth_params)
                if self._unroll(c, factor):
                    return True
                else:
                    del c.synth_params['unroll']
                    for b in c.region:
                        del b.synth_params['unroll']
            else:
                if self._unroll_loop_tree_leaf(c):
                    return True
                if c.synth_params['unroll']:
                    fail((self.scope, c.head.stms[0].lineno), Errors.RULE_UNROLL_NESTED_LOOP)
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

    def _unroll(self, cblk, factor):
        if factor == 1:
            return False
        assert self.scope.loop_nest_tree.is_leaf(cblk)
        assert cblk.loop_info
        assert cblk.loop_info.counter
        assert cblk.loop_info.init
        assert cblk.loop_info.update
        assert cblk.loop_info.cond
        if len(cblk.bodies) > 1:
            for b in cblk.bodies:
                if len(b.succs) > 1:
                    fail((self.scope, cblk.head.stms[0].lineno), Errors.RULE_UNROLL_CONTROL_BRANCH)
        assert len(cblk.bodies) == 1
        ret = self._find_loop_range(cblk)
        if not ret:
            fail((self.scope, cblk.head.stms[0].lineno), Errors.RULE_UNROLL_UNFIXED_LOOP)
        loop_min, loop_max, loop_step = ret
        initial_trip = ((loop_max + loop_step) - loop_min) // loop_step
        if initial_trip < 1:
            return False
        if factor == -1 or factor > loop_max:
            factor = initial_trip
        unroll_trip = initial_trip // factor
        unroll_remain = initial_trip % factor
        is_full_unroll = factor == initial_trip
        origin_body = cblk.bodies[0]
        defsyms = self.scope.usedef.get_syms_defined_at(cblk.head)
        origin_ivs = [sym for sym in defsyms if sym.is_induction()]
        new_ivs = self._new_ivs(factor, origin_ivs, is_full_unroll)
        if is_full_unroll:
            unroll_head, iv_updates = self._make_full_unroll_head(cblk, new_ivs, loop_min)
        else:
            unroll_head, iv_updates, lphis = self._make_unroll_head(cblk,
                                                                    loop_max,
                                                                    factor,
                                                                    new_ivs)
        defsyms = self.scope.usedef.get_syms_defined_at(origin_body)
        unroll_blks = self._make_unrolling_blocks(origin_body,
                                                  defsyms,
                                                  new_ivs,
                                                  iv_updates,
                                                  factor,
                                                  loop_min,
                                                  loop_step,
                                                  unroll_head)
        if is_full_unroll:
            self._reconnect_full_unroll_blocks(cblk, unroll_head, unroll_blks)
            self._replace_outer_uses(cblk, new_ivs, factor)
            parent = self.scope.loop_nest_tree.get_parent_of(cblk)
            self.scope.loop_nest_tree.del_edge(parent, cblk)
            if isinstance(cblk.parent, CompositBlock):
                offs = cblk.parent.bodies.index(cblk)
                cblk.parent.bodies.remove(cblk)
                for i, ublk in enumerate([unroll_head] + unroll_blks):
                    cblk.parent.bodies.insert(offs + i, ublk)
                    ublk.parent = cblk.parent
        else:
            new_cblk = CompositBlock(self.scope, unroll_head, unroll_blks, [unroll_head] + unroll_blks)
            self._reconnect_unroll_blocks(cblk, new_cblk, unroll_head, unroll_blks, lphis)
            parent = self.scope.loop_nest_tree.get_parent_of(cblk)
            self.scope.loop_nest_tree.del_edge(parent, cblk)
            self.scope.loop_nest_tree.add_edge(parent, new_cblk)
            if isinstance(cblk.parent, CompositBlock):
                utils.replace_item(parent.bodies, cblk, new_cblk)
                new_cblk.parent = parent
                new_cblk.synth_params = cblk.synth_params.copy()
                for i, ublk in enumerate([unroll_head] + unroll_blks):
                    ublk.parent = new_cblk
            del new_cblk.synth_params['unroll']
            if unroll_remain:
                # TODO:
                assert False
                remain_init = loop_min + (unroll_trip * loop_step * factor)
                self._make_remain_loop(blk, remain_init)
            self._replace_outer_uses(cblk, new_ivs, 0)
        for blk in [unroll_head] + unroll_blks:
            blk.synth_params = cblk.preds[0].synth_params.copy()
        return True

    def _reconnect_full_unroll_blocks(self, cblk, unroll_head, unroll_blks):
        loop_pred = cblk.head.preds[0]
        loop_exit = cblk.head.succs[1]

        # loop_pred -> unroll_head
        loop_pred.replace_succ(cblk, unroll_head)
        assert not loop_pred.succs_loop
        jmp = loop_pred.stms[-1]
        if jmp.is_a(JUMP):
            #assert jmp.target is cblk.head
            jmp.target = unroll_head
        elif jmp.is_a(CJUMP):
            assert jmp.true is cblk.head
            jmp.true = unroll_head
        else:
            assert False
        unroll_head.preds = [loop_pred]
        unroll_head.preds_loop = []

        first_blk = unroll_blks[0]
        last_blk = unroll_blks[-1]

        # unroll_head -> first_blk
        unroll_head.succs = [first_blk]
        assert not unroll_head.succs_loop
        assert unroll_head in first_blk.preds and len(first_blk.preds) == 1
        jmp = unroll_head.stms[-1]
        jmp.target = unroll_blks[0]
        jmp.false = loop_exit

        # last_blk -> loop_exit
        last_blk.succs = [loop_exit]
        last_blk.succs_loop = []
        loop_exit.preds = [last_blk]
        jmp = last_blk.stms[-1]
        assert jmp.is_a(JUMP)
        jmp.typ = ''
        jmp.target = loop_exit

    def _reconnect_unroll_blocks(self, cblk, new_cblk, unroll_head, unroll_blks, lphis):
        loop_pred = cblk.head.preds[0]
        loop_exit = cblk.head.succs[1]

        # loop_pred -> unroll_head
        loop_pred.replace_succ(cblk, new_cblk)
        assert new_cblk.preds[0] is loop_pred
        assert not loop_pred.succs_loop
        jmp = loop_pred.stms[-1]
        if jmp.is_a(JUMP):
            #assert jmp.target is cblk.head
            jmp.target = unroll_head
        elif jmp.is_a(CJUMP):
            assert jmp.true is cblk.head
            jmp.true = unroll_head
        else:
            assert False

        first_blk = unroll_blks[0]
        last_blk = unroll_blks[-1]

        # unroll_head -> first_blk | loop_exit
        unroll_head.succs = [first_blk, loop_exit]
        new_cblk.succs = [loop_exit]
        assert not unroll_head.succs_loop
        loop_exit.preds = [unroll_head]
        cjmp = unroll_head.stms[-1]
        cjmp.true = first_blk
        cjmp.false = loop_exit

        # last_blk -> unroll_head
        last_blk.succs = [unroll_head]
        last_blk.succs_loop = [unroll_head]
        unroll_head.preds = [loop_pred, last_blk]
        unroll_head.preds_loop = [last_blk]
        for lphi in lphis:
            lphi.defblks = [loop_pred, last_blk]
        jmp = last_blk.stms[-1]
        assert jmp.is_a(JUMP)
        assert jmp.typ == 'L'
        jmp.target = unroll_head

    def _make_full_unroll_head(self, cblk, new_ivs, loop_min):
        unroll_head, stm_map = self._clone_block(cblk.head, 'unroll_head')
        head_stms = []
        iv_updates = {}
        # append initial move for each lphi
        #  i#2 = phi(init, i#3)  -> i#2_0 = 0
        #  x#2 = phi(x_init, x#3)  -> x#2_0 = x_init
        for _, stm in stm_map.items():
            if stm.is_a(LPHI):
                assert len(stm.args) == 2
                orig_sym = stm.var.symbol()
                new_sym_0 = new_ivs[orig_sym][0]
                dst = TEMP(new_sym_0, Ctx.STORE)
                src = stm.args[0]
                iv_updates[stm.args[1].symbol()] = new_ivs[orig_sym]
                mv = MOVE(dst, src)
                mv.lineno = dst.lineno = src.lineno = stm.args[0].lineno
                head_stms.append(mv)
        orig_cjump_cond = unroll_head.stms[-2]
        assert orig_cjump_cond.is_a(MOVE) and orig_cjump_cond.src.is_a(RELOP)
        src = CONST(1)
        mv = MOVE(orig_cjump_cond.dst.clone(), src)
        mv.lineno = src.lineno = orig_cjump_cond.lineno
        head_stms.append(mv)
        orig_cjump = unroll_head.stms[-1]
        assert orig_cjump.is_a(CJUMP)
        jump = JUMP(None)
        jump.lineno = orig_cjump
        head_stms.append(jump)

        unroll_head.stms = []
        for stm in head_stms:
            unroll_head.append_stm(stm)
        return unroll_head, iv_updates

    def _make_unroll_head(self, cblk, loop_max, factor, new_ivs):
        unroll_head, stm_map = self._clone_block(cblk.head, 'unroll_head')
        head_stms = []
        iv_updates = {}
        lphis = []
        # append modified lphi
        #  i#2 = phi(init, i#3)  -> i#2_0 = phi(0, i#2_n)
        #  x#2 = phi(x_init, x#3)  -> x#2_0 = phi(x_init, x#2_n)
        for _, stm in stm_map.items():
            if stm.is_a(LPHI):
                assert len(stm.args) == 2
                orig_sym = stm.var.symbol()
                new_sym_0 = new_ivs[orig_sym][0]
                new_sym_n = new_ivs[orig_sym][factor]
                stm.var.set_symbol(new_sym_0)
                iv_updates[stm.args[1].symbol()] = new_ivs[orig_sym]
                stm.args[1].set_symbol(new_sym_n)
                head_stms.append(stm)
                lphis.append(stm)

        orig_cjump_cond = unroll_head.stms[-2]
        assert orig_cjump_cond.is_a(MOVE) and orig_cjump_cond.src.is_a(RELOP)
        cond_sym = orig_cjump_cond.dst.symbol()
        orig_cjump = unroll_head.stms[-1]
        assert orig_cjump.is_a(CJUMP)
        new_loop_iv = new_ivs[cblk.loop_info.counter][0]
        cond_rhs = RELOP('Lt', TEMP(new_loop_iv, Ctx.LOAD), CONST(loop_max))
        #cond_sym = self.scope.add_condition_sym()
        cond_lhs = TEMP(cond_sym, Ctx.STORE)
        cond_stm = MOVE(cond_lhs, cond_rhs)
        cond_rhs.lineno = cond_lhs.lineno = cond_stm.lineno = orig_cjump.lineno
        head_stms.append(cond_stm)
        cond_exp = TEMP(cond_sym, Ctx.LOAD)
        cjump = CJUMP(cond_exp, None, None)
        cjump.lineno = cond_exp.lineno = orig_cjump
        head_stms.append(cjump)

        unroll_head.stms = []
        for stm in head_stms:
            unroll_head.append_stm(stm)
        return unroll_head, iv_updates, lphis

    def _clone_block(self, blk, nametag):
        stm_map = {}
        clone_blk = blk.clone(self.scope, stm_map, nametag)
        return clone_blk, stm_map

    def _make_unrolling_blocks(self, origin_block, defsyms, new_ivs, iv_updates, factor, offset, step, head):
        pred_blk = head
        assert factor > 0
        new_blks = []
        for i in range(factor):
            new_blk, stm_map = self._clone_block(origin_block, 'unroll_body')
            new_blk.preds_loop = []
            new_blk.succs_loop = []
            replacer = IVReplacer(self.scope, defsyms, new_ivs, iv_updates, i)
            for stm in new_blk.stms:
                replacer.visit(stm)
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

    def _new_ivs(self, factor, ivs, is_full_unroll):
        new_iv_map = defaultdict(list)
        for i in range(factor + 1):
            for iv in ivs:
                new_name = '{}_{}'.format(iv.name, i)
                new_iv = self.scope.inherit_sym(iv, new_name)
                new_iv_map[iv].append(new_iv)
                if i != 0 or is_full_unroll:
                    new_iv.del_tag('induction')
        return new_iv_map

    def _make_remain_loop(self, blk, remina_init):
        pass

    def _replace_outer_uses(self, cblk, new_ivs, index):
        for u in cblk.outer_uses:
            usestms = self.scope.usedef.get_stms_using(u)
            for ustm in usestms:
                ustm.replace(u, new_ivs[u][index])

    def _find_loop_range(self, blk):
        loop_min = self._find_loop_min(blk.loop_info)
        if not isinstance(loop_min, int):
            return None
        loop_max = self._find_loop_max(blk.loop_info)
        if not isinstance(loop_max, int):
            return None
        loop_step = self._find_loop_step(blk.loop_info)
        if not isinstance(loop_step, int):
            return None
        return (loop_min, loop_max, loop_step)

    def _find_loop_min(self, loop_info):
        if loop_info.init.is_a(CONST):
            return loop_info.init.value
        return None

    def _find_loop_max(self, loop_info):
        loop_cond_sym = loop_info.cond
        loop_cond_defs = self.scope.usedef.get_stms_defining(loop_cond_sym)
        assert len(loop_cond_defs) == 1
        loop_cond_stm = list(loop_cond_defs)[0]
        assert loop_cond_stm.is_a(MOVE)
        loop_cond_rhs = loop_cond_stm.src
        if loop_cond_rhs.is_a(RELOP):
            # We focus on simple increasing loops
            if loop_cond_rhs.op in ('Lt', 'LtE'):
                if loop_cond_rhs.left.symbol() is loop_info.counter:
                    may_max = loop_cond_rhs.right
                elif loop_cond_rhs.right.symbol() is loop_info.counter:
                    may_max = loop_cond_rhs.left
                else:
                    return None
                if may_max.is_a(CONST):
                    if loop_cond_rhs.op == 'Lt':
                        return may_max.value - 1
                    else:
                        return may_max.value
                return None
        raise NotImplementedError('others than increasing loop are not supported')

    def _find_loop_step(self, loop_info):
        loop_update = loop_info.update
        assert loop_update.is_a(TEMP)
        update_sym = loop_update.symbol()
        update_defs = self.scope.usedef.get_stms_defining(update_sym)
        assert len(update_defs) == 1
        update_stm = list(update_defs)[0]
        assert update_stm.is_a(MOVE)
        update_rhs = update_stm.src
        if update_rhs.is_a(BINOP):
            if update_rhs.op == 'Add':
                if update_rhs.left.symbol() is loop_info.counter:
                    may_step = update_rhs.right
                elif update_rhs.right.symbol() is loop_info.counter:
                    may_step = update_rhs.left
                else:
                    return None
                if may_step.is_a(CONST):
                    return may_step.value
                return None
        raise NotImplementedError('others than increasing loop are not supported')


class IVReplacer(IRVisitor):
    def __init__(self, scope, defsyms, new_ivs, iv_updates, idx):
        self.scope = scope
        self.defsyms = defsyms
        self.new_ivs = new_ivs
        self.iv_updates = iv_updates
        self.idx = idx

    def visit_TEMP(self, ir):
        if ir.sym not in self.defsyms and ir.sym not in self.new_ivs.keys():
            # this is loop invariant
            return
        if not ir.sym.typ.is_scalar():
            return
        if ir.sym.is_induction():
            assert ir.sym in self.new_ivs.keys()
            new_sym = self.new_ivs[ir.sym][self.idx]
        elif ir.sym in self.iv_updates:
            new_ivs = self.iv_updates[ir.sym]
            new_sym = new_ivs[self.idx + 1]
        else:
            new_name = '{}_{}'.format(ir.sym.name, self.idx)
            new_sym = self.scope.inherit_sym(ir.sym, new_name)
        ir.set_symbol(new_sym)
