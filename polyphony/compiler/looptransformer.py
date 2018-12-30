from .block import Block
from .ir import Ctx, CONST, UNOP, RELOP, TEMP, JUMP, MOVE, PHIBase, PHI, LPHI
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
            if not self.scope.is_leaf_region(loop) and loop.head.synth_params['scheduling'] == 'pipeline':
                self._flatten(loop)
                ret = True
        return ret

    def _build_diamond_block(self, loop, subloop):
        # transform loop to diamond blocks
        #       head
        #      /    \
        #   body    body_else
        #      \    /
        #       exit
        subloop_exit = subloop.exits[0]
        subloop_body = subloop.head.succs[0]
        subloop_body_else = Block(self.scope, subloop_body.nametag + 'else')
        subloop_body_else.order = subloop_body.order
        subloop_body_else.path_exp = RELOP('And',
                                           TEMP(loop.cond, Ctx.LOAD, lineno=0),
                                           UNOP('Not', TEMP(subloop.cond, Ctx.LOAD, lineno=0), lineno=0),
                                           lineno=0)
        subloop.head.remove_pred(subloop_body)
        subloop.head.replace_succ(subloop_exit, subloop_body_else)
        subloop_body.replace_succ(subloop.head, subloop_exit)
        subloop_body.succs_loop = []
        jmp = subloop_body.stms[-1]
        jmp.typ = ''
        subloop_body_else.preds = [subloop.head]
        subloop_body_else.connect(subloop_exit)
        subloop_exit.preds = [subloop_body, subloop_body_else]
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

        removes = []
        nested_outer_lphis = {}
        nested_inner_lphis = {}
        outer_phi_ps = []
        for lphi in loop.head.collect_stms(LPHI):
            inner_lphi = self._find_nested_lphi(lphi)
            if inner_lphi:
                nested_inner_lphis[inner_lphi] = lphi
                nested_outer_lphis[lphi] = inner_lphi
        for subloop in self.scope.child_regions(loop):
            if len(subloop.bodies) != 1:
                # TODO: error
                assert 'cannot flatten'
            assert len(subloop.exits) == 1
            loop_lineno = subloop.update.lineno
            subloop_body, subloop_body_else, subloop_exit = self._build_diamond_block(loop, subloop)

            # setup else block
            subloop_body_else.append_stm(JUMP(subloop_exit, lineno=0))
            self._move_stms(subloop_exit, subloop_body_else)
            subloop_exit.stms = [subloop_exit.stms[-1]]
            if master_continue in subloop_exit.succs:
                self._move_stms(master_continue, subloop_body_else)

            body_cond = RELOP('And',
                              TEMP(loop.cond, Ctx.LOAD, lineno=loop_lineno),
                              TEMP(subloop.cond, Ctx.LOAD, lineno=loop_lineno),
                              lineno=loop_lineno)
            else_cond = RELOP('And',
                              TEMP(loop.cond, Ctx.LOAD, lineno=loop_lineno),
                              UNOP('Not', TEMP(subloop.cond, Ctx.LOAD, lineno=loop_lineno), lineno=loop_lineno),
                              lineno=loop_lineno)
            init_flag, init_lphi = self._insert_init_flag(loop, body_cond, else_cond)

            # deal with phi for induction variables
            for lphi in subloop.head.collect_stms(LPHI):
                assert lphi.args[1].is_a(TEMP)
                var_t = lphi.var.symbol().typ
                psi_sym = self.scope.add_temp(typ=var_t)
                psi = PHI(TEMP(psi_sym, Ctx.STORE, lineno=lphi.lineno), lineno=lphi.lineno)
                if lphi in nested_inner_lphis:
                    outer_lphi = nested_inner_lphis[lphi]
                    psi.args = [
                        lphi.args[1].clone(),
                        outer_lphi.args[1].clone()
                    ]
                    psi.ps = [
                        body_cond.clone(),
                        else_cond.clone()
                    ]
                    lphi.args[1] = TEMP(outer_lphi.var.symbol(),
                                        Ctx.LOAD, lineno=lphi.lineno)
                    outer_lphi.args[1] = TEMP(psi_sym,
                                              Ctx.LOAD, lineno=outer_lphi.lineno)
                else:
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
            removes.append(subloop)

        # deal with outer lphis
        for lphi in loop.head.collect_stms(LPHI):
            if lphi in nested_outer_lphis:
                continue
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
        for subloop in removes:
            self.scope.remove_region(subloop)

    def _def_stm(self, sym):
        defs = self.scope.usedef.get_stms_defining(sym)
        assert len(defs) == 1
        return list(defs)[0]

    def _find_nested_lphi(self, outer_lphi):
        def find_inner_lphi(stm, outer_lphi, var):
            if stm.is_a(LPHI):
                if stm is outer_lphi:
                    return None
                if stm.var.symbol().ancestor is outer_lphi.var.symbol().ancestor:
                    return stm
                return None
            elif stm.is_a(MOVE):
                for use in self.scope.usedef.get_stms_using(stm.dst.symbol()):
                    inner_lphi = find_inner_lphi(use, outer_lphi, stm.dst)
                    if inner_lphi:
                        return inner_lphi
            return None

        def find_outer_lphi(stm, inner_lphi, var):
            if stm.is_a(LPHI):
                if stm is inner_lphi:
                    return False
                if stm.var.symbol().ancestor is inner_lphi.var.symbol().ancestor:
                    return True
                return False
            elif stm.is_a(MOVE):
                uses = self.scope.usedef.get_stms_using(stm.dst.symbol())
                for use in uses:
                    if find_outer_lphi(use, inner_lphi, stm.dst):
                        return True
            return False
        for use in self.scope.usedef.get_stms_using(outer_lphi.var.symbol()):
            inner_lphi = find_inner_lphi(use, outer_lphi, outer_lphi.var)
            if not inner_lphi:
                continue
            for _use in self.scope.usedef.get_stms_using(inner_lphi.var.symbol()):
                if find_outer_lphi(_use, inner_lphi, inner_lphi.var):
                    return inner_lphi
        return None

    def _is_loop_head(self, blk):
        return len(blk.preds_loop) > 0

    def _move_stms(self, blk_src, blk_dst):
        for stm in blk_src.stms[:-1]:
            blk_dst.insert_stm(-1, stm)
        blk_src.stms = [blk_src.stms[-1]]
