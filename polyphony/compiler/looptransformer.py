from .block import Block
from .cfgopt import HyperBlockBuilder
from .ir import Ctx, CONST, UNOP, RELOP, TEMP, MOVE, JUMP, CJUMP, PHIBase, PHI, LPHI
from .loop import Region, Loop
from .usedef import UseDefDetector
from .utils import replace_item
from logging import getLogger
logger = getLogger(__name__)


class FlattenLoop(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        #self.hyperblock_builder = HyperBlockBuilder()
        #self.hyperblock_builder.scope = scope
        #self.hyperblock_builder.uddetector = UseDefDetector()
        #self.hyperblock_builder.uddetector.table = scope.usedef
        for loop in self.scope.child_regions(self.scope.top_region()):
            if not self.scope.is_leaf_region(loop) and loop.head.synth_params['scheduling'] == 'pipeline':
                self._flatten(loop)

    def _flatten(self, loop):
        master_continue = loop.head.preds_loop[0]
        master_cnt_defs = self.scope.usedef.get_stms_defining(loop.counter)
        assert len(master_cnt_defs) == 1
        master_cnt_lphi = list(master_cnt_defs)[0]
        assert master_cnt_lphi.is_a(LPHI)
        master_cnt_update_defs = self.scope.usedef.get_stms_defining(loop.update.symbol())
        assert len(master_cnt_update_defs) == 1
        master_cnt_update_def = list(master_cnt_update_defs)[0]
        removes = []
        for subloop in self.scope.child_regions(loop):
            if len(subloop.bodies) != 1:
                # TODO: error
                assert 'cannot flatten'
            assert len(subloop.exits) == 1
            assert subloop.exits[0] is master_continue
            subloop_exit = master_continue
            subloop_body = subloop.bodies[0]
            subloop_body_else = Block(self.scope, subloop_body.nametag + 'else')
            subloop_body_else.order = subloop_body.order
            subloop_body_else.path_exp = RELOP('And',
                                               TEMP(loop.cond, Ctx.LOAD, lineno=0),
                                               UNOP('Not', TEMP(subloop.cond, Ctx.LOAD, lineno=0), lineno=0),
                                               lineno=0)
            # transform loop to diamond blocks
            #       head
            #      /    \
            #   body    body_else
            #      \    /
            #       exit
            subloop.head.remove_pred(subloop_body)
            subloop.head.replace_succ(subloop_exit, subloop_body_else)

            subloop_body.replace_succ(subloop.head, subloop_exit)
            subloop_body.succs_loop = []
            jmp = subloop_body.stms[-1]
            jmp.typ = ''
            subloop_body_else.preds = [subloop.head]
            subloop_body_else.connect(subloop_exit)
            subloop_exit.preds = [subloop_body, subloop_body_else]

            cnt_defs = self.scope.usedef.get_stms_defining(subloop.counter)
            assert len(cnt_defs) == 1
            cnt_lphi = list(cnt_defs)[0]
            assert cnt_lphi.is_a(LPHI)
            # move subloop's lphi
            subloop.head.stms.remove(cnt_lphi)
            loop.head.insert_stm(-1, cnt_lphi)

            # setup else block
            jmp = JUMP(subloop_exit, lineno=0)
            for stm in subloop_exit.stms[:-1]:
                subloop_body_else.append_stm(stm)
            subloop_exit.stms = [subloop_exit.stms[-1]]
            subloop_body_else.append_stm(jmp)

            # deal with phi for loop counter
            cnt_update_defs = self.scope.usedef.get_stms_defining(subloop.update.symbol())
            assert len(cnt_update_defs) == 1
            cnt_update_def = list(cnt_update_defs)[0]

            # sub counter phi
            ps = [
                RELOP('And',
                      TEMP(loop.cond, Ctx.LOAD, lineno=0),
                      TEMP(subloop.cond, Ctx.LOAD, lineno=0),
                      lineno=0),
                RELOP('And',
                      TEMP(loop.cond, Ctx.LOAD, lineno=0),
                      UNOP('Not', TEMP(subloop.cond, Ctx.LOAD, lineno=0), lineno=0),
                      lineno=0),
            ]
            args = [
                cnt_update_def.dst.clone(),  # j += 1
                subloop.init.clone()         # j = init
            ]
            sub_cnt_phi = self._counter_phi(args, ps)
            subloop_exit.insert_stm(0, sub_cnt_phi)
            # replace
            cnt_lphi.replace(subloop.update.symbol(), sub_cnt_phi.var.symbol())

            # master counter phi
            args = [
                master_cnt_lphi.var.clone(),  # i = 0 or i = i
                master_cnt_update_def.dst.clone()  # i += 1
            ]
            master_cnt_phi = self._counter_phi(args, ps)
            subloop_exit.insert_stm(1, master_cnt_phi)
            # replace
            master_cnt_lphi.replace(loop.update.symbol(), master_cnt_phi.var.symbol())

            subloop.head.synth_params['scheduling'] = 'pipeline'
            removes.append(subloop)
        for subloop in removes:
            self.scope.remove_region(subloop)

    def _counter_phi(self, args, ps):
        phi_sym = self.scope.add_temp()
        phi_var = TEMP(phi_sym, Ctx.STORE, lineno=0)
        phi = PHI(phi_var, lineno=0)
        phi.args = args[:]
        for a in args:
            a.ctx = Ctx.LOAD
        phi_sym.typ = args[0].symbol().typ
        phi.ps = ps[:]
        return phi
