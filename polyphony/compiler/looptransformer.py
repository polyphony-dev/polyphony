from .block import Block
from .common import fail
from .errors import Errors
from .ir import Ctx, CONST, UNOP, RELOP, TEMP, JUMP, PHI, LPHI
from .type import Type
from logging import getLogger
logger = getLogger(__name__)


class LoopFlatten(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        ret = False
        for loop in self.scope.child_regions(self.scope.top_region()):
            if (not self.scope.is_leaf_region(loop) and
                    loop.head.synth_params['scheduling'] == 'pipeline'):
                self._flatten(loop)
                ret = True
        return ret

    def _build_diamond_block(self, loop, subloop):
        # transform loop to diamond blocks
        #       head
        #      /    \
        #   body    body_else
        #      \    /
        #       tail
        subloop_exit = subloop.exits[0]
        subloop_body = subloop.head.succs[0]
        assert len(subloop.head.preds_loop) == 1
        sub_continue = subloop.head.preds_loop[0]
        subloop_body_else = Block(self.scope, subloop_body.nametag + 'else')
        subloop_body_else.order = subloop_body.order
        outer_cond = subloop_exit.path_exp
        subloop_body_else.path_exp = RELOP('And',
                                           outer_cond.clone(),
                                           UNOP('Not', TEMP(subloop.cond, Ctx.LOAD, lineno=0), lineno=0),
                                           lineno=0)
        subloop.head.remove_pred(sub_continue)
        subloop.head.replace_succ(subloop_exit, subloop_body_else)
        sub_continue.replace_succ(subloop.head, subloop_exit)
        sub_continue.succs_loop = []
        jmp = subloop_body.stms[-1]
        jmp.typ = ''
        subloop_body_else.preds = [subloop.head]
        subloop_body_else.connect(subloop_exit)
        subloop_exit.preds = [sub_continue, subloop_body_else]
        return subloop_body, subloop_body_else, subloop_exit

    def _insert_init_flag(self, loop, body_cond, else_cond):
        init_sym = self.scope.add_temp('init', {'induction'}, typ=Type.bool_t)
        init_update_sym = self.scope.add_temp('init_update', typ=Type.bool_t)
        init_lphi = LPHI(TEMP(init_sym, Ctx.STORE, lineno=0), lineno=0)
        init_lphi.args = [
            CONST(True),
            TEMP(init_update_sym, Ctx.LOAD, lineno=0)
        ]
        init_lphi.ps = [CONST(1)] * 2
        loop.head.insert_stm(-1, init_lphi)

        loop_continue = loop.head.preds_loop[0]
        update_phi = PHI(TEMP(init_update_sym, Ctx.STORE, lineno=0), lineno=0)
        update_phi.args = [
            CONST(False),
            CONST(True)
        ]
        update_phi.ps = [
            body_cond.clone(),
            else_cond.clone()
        ]
        loop_continue.insert_stm(0, update_phi)
        return init_sym, init_lphi

    def _lphi_to_psi(self, lphi, cond):
        psi = PHI(lphi.var, lineno=lphi.lineno)
        psi.args = lphi.args[:]
        psi.ps = [
            TEMP(cond, Ctx.LOAD, lineno=0),
            UNOP('Not', TEMP(cond, Ctx.LOAD, lineno=0), lineno=0)
        ]
        idx = lphi.block.stms.index(lphi)
        lphi.block.stms.remove(lphi)
        lphi.block.insert_stm(idx, psi)

    def _flatten(self, loop):
        master_continue = loop.head.preds_loop[0]
        master_body = loop.head.succs[0]
        if not self._is_loop_head(master_body):
            self._move_stms(master_body, loop.head)

        outer_phi_ps = []
        subloops = self.scope.child_regions(loop)
        if len(subloops) > 1:
            fail((self.scope, subloops.orders()[1].update.lineno), Errors.RULE_PIPELINE_CANNNOT_FLATTEN)

        subloop = subloops.orders()[0]
        if not self.scope.is_leaf_region(subloop):
            self._flatten(subloop)
        assert len(subloop.exits) == 1
        loop_lineno = subloop.update.lineno
        subloop_body, subloop_body_else, subloop_exit = self._build_diamond_block(loop, subloop)

        # setup else block
        subloop_body_else.append_stm(JUMP(subloop_exit, lineno=0))
        self._move_stms(subloop_exit, subloop_body_else)
        subloop_exit.stms = [subloop_exit.stms[-1]]
        if master_continue in subloop_exit.succs:
            self._move_stms(master_continue, subloop_body_else)
        outer_cond = subloop_exit.path_exp
        body_cond = RELOP('And',
                          outer_cond.clone(),
                          TEMP(subloop.cond, Ctx.LOAD, lineno=loop_lineno),
                          lineno=loop_lineno)
        else_cond = RELOP('And',
                          outer_cond.clone(),
                          UNOP('Not', TEMP(subloop.cond, Ctx.LOAD, lineno=loop_lineno), lineno=loop_lineno),
                          lineno=loop_lineno)
        init_flag, init_lphi = self._insert_init_flag(loop, body_cond, else_cond)

        # deal with phi for induction variables
        for lphi in subloop.head.collect_stms(LPHI):
            assert lphi.args[1].is_a(TEMP)
            var_t = lphi.var.symbol().typ
            psi_sym = self.scope.add_temp(typ=var_t)
            psi = PHI(TEMP(psi_sym, Ctx.STORE, lineno=lphi.lineno), lineno=lphi.lineno)
            psi.args = [
                lphi.args[1].clone(),
                TEMP(lphi.var.symbol(), Ctx.LOAD, lineno=lphi.lineno)
            ]
            psi.ps = [
                body_cond,
                else_cond
            ]
            lphi.args[1] = TEMP(psi_sym, Ctx.LOAD, lineno=lphi.lineno)
            subloop_exit.insert_stm(-1, psi)
            self._lphi_to_psi(lphi, init_flag)
        # TODO
        outer_phi_ps = [
            body_cond,
            else_cond
        ]
        subloop.head.synth_params['scheduling'] = 'pipeline'
        for blk in subloop.bodies:
            blk.synth_params['scheduling'] = 'pipeline'
        subloop_body_else.synth_params['scheduling'] = 'pipeline'
        subloop_exit.synth_params['scheduling'] = 'pipeline'

        # deal with outer lphis
        for lphi in loop.head.collect_stms(LPHI):
            if lphi is init_lphi:
                continue
            psi_sym = self.scope.add_temp(typ=lphi.var.symbol().typ)
            psi = PHI(TEMP(psi_sym, Ctx.STORE, lineno=lphi.lineno), lineno=lphi.lineno)
            psi.args = [
                TEMP(lphi.var.symbol(), Ctx.LOAD, lineno=lphi.lineno),
                lphi.args[1].clone()
            ]
            psi.ps = outer_phi_ps
            lphi.args[1] = TEMP(psi_sym, Ctx.LOAD, lineno=lphi.lineno)
            loop.head.preds[1].insert_stm(-1, psi)
        logger.debug(str(self.scope))

    def _def_stm(self, sym):
        defs = self.scope.usedef.get_stms_defining(sym)
        assert len(defs) == 1
        return list(defs)[0]

    def _is_loop_head(self, blk):
        return len(blk.preds_loop) > 0

    def _move_stms(self, blk_src, blk_dst):
        for stm in blk_src.stms[:-1]:
            blk_dst.insert_stm(-1, stm)
        blk_src.stms = [blk_src.stms[-1]]
