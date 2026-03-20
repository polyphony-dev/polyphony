"""Loop flattening using new IR (ir.py).

Flattens nested loops into single loops when the outer loop is marked
for pipeline scheduling.
"""
from ..block import Block
from ..ir import (
    Ctx, Const, Temp, UnOp, RelOp, Move, Jump, CJump, Phi, LPhi, Expr,
)
from ..irhelper import qualified_symbols
from ..types.type import Type
from ..symbol import Symbol
from ..analysis.usedef import UseDefDetector
from ...common.common import fail
from ...common.errors import Errors
from logging import getLogger
logger = getLogger(__name__)


class LoopFlatten(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.usedef = UseDefDetector().process(scope)
        ret = False
        for loop in self.scope.child_regions(self.scope.top_region()):
            if (not self.scope.is_leaf_region(loop) and
                    loop.head.synth_params['scheduling'] == 'pipeline'):
                self._flatten(loop)
                ret = True
        return ret

    def _build_diamond_block(self, loop, subloop):
        # Transform loop to diamond blocks:
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
        subloop_body_else.path_exp = RelOp(
            op='And',
            left=outer_cond.model_copy(deep=True),
            right=UnOp(op='Not', exp=Temp(name=subloop.cond.name)))
        subloop.head.remove_pred(sub_continue)
        subloop.head.replace_succ(subloop_exit, subloop_body_else)
        sub_continue.replace_succ(subloop.head, subloop_exit)
        sub_continue.succs_loop = []
        jmp = subloop_body.stms[-1]
        if isinstance(jmp, Jump):
            object.__setattr__(jmp, 'typ', '')
        subloop_body_else.preds = [subloop.head]
        subloop_body_else.connect(subloop_exit)
        subloop_exit.preds = [sub_continue, subloop_body_else]
        return subloop_body, subloop_body_else, subloop_exit

    def _insert_init_flag(self, loop, body_cond, else_cond):
        init_sym = self.scope.add_temp('init', {'induction'}, typ=Type.bool())
        init_update_sym = self.scope.add_temp('init_update', typ=Type.bool())
        init_lphi = LPhi(var=Temp(name=init_sym.name, ctx=Ctx.STORE),
                         args=(Const(value=True), Temp(name=init_update_sym.name)),
                         ps=(Const(value=1), Const(value=1)))
        object.__setattr__(init_lphi, 'block', loop.head.bid)
        loop.head.stms.insert(-1, init_lphi)

        loop_continue = loop.head.preds_loop[0]
        update_phi = Phi(var=Temp(name=init_update_sym.name, ctx=Ctx.STORE),
                         args=(Const(value=False), Const(value=True)),
                         ps=(body_cond.model_copy(deep=True), else_cond.model_copy(deep=True)))
        object.__setattr__(update_phi, 'block', loop_continue.bid)
        loop_continue.stms.insert(0, update_phi)
        return init_sym, init_lphi

    def _lphi_to_psi(self, lphi, cond):
        psi = Phi(var=lphi.var,
                  args=lphi.args,
                  ps=(Temp(name=cond.name), UnOp(op='Not', exp=Temp(name=cond.name))))
        lphi_blk = self.scope.find_block(lphi.block)
        idx = lphi_blk.stms.index(lphi)
        lphi_blk.stms.remove(lphi)
        object.__setattr__(psi, 'block', lphi.block)
        lphi_blk.stms.insert(idx, psi)

    def _flatten(self, loop):
        master_continue = loop.head.preds_loop[0]
        master_body = loop.head.succs[0]
        if not self._is_loop_head(master_body):
            self._move_stms(master_body, loop.head)

        subloops = self.scope.child_regions(loop)
        if len(subloops) > 1:
            fail(subloops.orders()[1].head.stms[-1],
                 Errors.RULE_PIPELINE_CANNNOT_FLATTEN)

        subloop = subloops.orders()[0]
        if not self.scope.is_leaf_region(subloop):
            self._flatten(subloop)
        assert len(subloop.exits) == 1
        subloop_body, subloop_body_else, subloop_exit = self._build_diamond_block(loop, subloop)

        # Set up else block
        jmp = Jump(target=subloop_exit.bid)
        object.__setattr__(jmp, 'block', subloop_body_else.bid)
        subloop_body_else.stms = [jmp]
        self._move_stms(subloop_exit, subloop_body_else)
        subloop_exit.stms = [subloop_exit.stms[-1]]
        if master_continue in subloop_exit.succs:
            self._move_stms(master_continue, subloop_body_else)

        outer_cond = subloop_exit.path_exp
        body_cond = RelOp(
            op='And',
            left=outer_cond.model_copy(deep=True),
            right=Temp(name=subloop.cond.name))
        else_cond = RelOp(
            op='And',
            left=outer_cond.model_copy(deep=True),
            right=UnOp(op='Not', exp=Temp(name=subloop.cond.name)))
        init_flag, init_lphi = self._insert_init_flag(loop, body_cond, else_cond)

        # Deal with phi for induction variables
        for lphi in subloop.head.collect_stms([LPhi]):
            assert isinstance(lphi.args[1], Temp)
            sym = qualified_symbols(lphi.var, self.scope)[-1]
            assert isinstance(sym, Symbol)
            var_t = sym.typ
            psi_sym = self.scope.add_temp(typ=var_t)
            psi = Phi(var=Temp(name=psi_sym.name, ctx=Ctx.STORE),
                      args=(lphi.args[1].model_copy(deep=True), Temp(name=lphi.var.name)),
                      ps=(body_cond, else_cond))
            object.__setattr__(lphi, 'args', lphi.args[:1] + (Temp(name=psi_sym.name),) + lphi.args[2:])
            object.__setattr__(psi, 'block', subloop_exit.bid)
            subloop_exit.stms.insert(-1, psi)
            self._lphi_to_psi(lphi, init_flag)

        subloop.head.synth_params['scheduling'] = 'pipeline'
        for blk in subloop.bodies:
            blk.synth_params['scheduling'] = 'pipeline'
        subloop_body_else.synth_params['scheduling'] = 'pipeline'
        subloop_exit.synth_params['scheduling'] = 'pipeline'

        # Deal with outer lphis
        for lphi in loop.head.collect_stms([LPhi]):
            if lphi is init_lphi:
                continue
            sym = qualified_symbols(lphi.var, self.scope)[-1]
            assert isinstance(sym, Symbol)
            psi_sym = self.scope.add_temp(typ=sym.typ)
            psi = Phi(var=Temp(name=psi_sym.name, ctx=Ctx.STORE),
                      args=(Temp(name=lphi.var.name), lphi.args[1].model_copy(deep=True)),
                      ps=(body_cond, else_cond))
            object.__setattr__(lphi, 'args', lphi.args[:1] + (Temp(name=psi_sym.name),) + lphi.args[2:])
            pred_blk = loop.head.preds[1]
            object.__setattr__(psi, 'block', pred_blk.bid)
            pred_blk.stms.insert(-1, psi)
        logger.debug(str(self.scope))

    def _def_stm(self, sym):
        defs = self.usedef.get_stms_defining(sym)
        assert len(defs) == 1
        return list(defs)[0]

    def _is_loop_head(self, blk):
        return len(blk.preds_loop) > 0

    def _move_stms(self, blk_src, blk_dst):
        for stm in blk_src.stms[:-1]:
            object.__setattr__(stm, 'block', blk_dst.bid)
            blk_dst.stms.insert(-1, stm)
        blk_src.stms = [blk_src.stms[-1]]
