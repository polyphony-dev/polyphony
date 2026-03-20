"""If transformers using new IR (ir.py).

IfTransformer: Merges chained if-elif-else (CJUMP chains) into MCJUMP.
IfCondTransformer: Converts MCJUMP conditions to mutually exclusive form.
"""
from ..ir import Const, Temp, UnOp, RelOp, Move, CJump, MCJump, Ctx
from ..types.type import Type
from logging import getLogger
logger = getLogger(__name__)


class IfTransformer(object):
    def process(self, scope):
        self.scope = scope
        for blk in scope.traverse_blocks():
            self._process_block(blk)

    def _merge_else_cj(self, cj, conds, targets):
        """Recursively merge chained else-if CJUMPs into a flat conds/targets list."""
        false_blk = self.scope.find_block(cj.false)
        if len(false_blk.stms) == 1 and isinstance(false_blk.stms[0], CJump):
            else_cj = false_blk.stms[0]
            false_blk.succs = []
            false_blk.preds = []
            false_blk.stms = []

            conds.append(else_cj.exp)
            targets.append(else_cj.true)
            if not self._merge_else_cj(else_cj, conds, targets):
                conds.append(Const(value=1))
                targets.append(else_cj.false)
            return True
        return False

    def _process_block(self, block):
        if not block.stms:
            return
        last = block.stms[-1]
        if not isinstance(last, CJump):
            return

        conds = []
        targets = []
        cj = last
        conds.append(cj.exp)
        targets.append(cj.true)
        if self._merge_else_cj(cj, conds, targets):
            block.stms.pop()
            mj = MCJump(conds=conds, targets=targets, loc=cj.loc, block=block.bid)
            block.stms.append(mj)
            block.succs = []
            for target_bid in targets:
                target_blk = self.scope.find_block(target_bid)
                target_blk.preds = [block]
                block.succs.append(target_blk)
                logger.debug('target.block ' + target_blk.name)
            logger.debug(str(mj))


class IfCondTransformer(object):
    """Converts MCJUMP conditions to mutually exclusive form.

    if p0:   ...          =>  if p0:   ...
    elif p1: ...              if !p0 and p1: ...
    elif p2: ...              if !p0 and !p1 and p2: ...
    else:    ...              if !p0 and !p1 and !p2: ...
    """
    def process(self, scope):
        self.scope = scope
        for blk in scope.traverse_blocks():
            self._process_block(blk)

    def _process_block(self, block):
        if not block.stms:
            return
        last = block.stms[-1]
        if not isinstance(last, MCJump):
            return
        mj = last
        for c in mj.conds:
            assert isinstance(c, (Temp, Const))
        prevs = []
        new_cond_exps = []
        for c in mj.conds:
            new_c = None
            for prev_c in prevs:
                if new_c:
                    new_c = RelOp(op='And', left=new_c, right=UnOp(op='Not', exp=prev_c))
                else:
                    new_c = UnOp(op='Not', exp=prev_c)
            if new_c:
                if isinstance(c, Const):
                    assert c.value == 1
                else:
                    new_c = RelOp(op='And', left=new_c, right=c)
            else:
                new_c = c
            new_cond_exps.append(new_c)
            prevs.append(c)
        new_conds = []
        mj_idx = len(block.stms) - 1
        insert_pos = mj_idx
        for c in new_cond_exps:
            if isinstance(c, Temp):
                new_conds.append(c)
            else:
                new_sym = self.scope.add_condition_sym()
                new_sym.typ = Type.bool()
                mv = Move(
                    dst=Temp(name=new_sym.name, ctx=Ctx.STORE),
                    src=c,
                    block=block.bid,
                )
                block.stms.insert(insert_pos, mv)
                insert_pos += 1
                new_conds.append(Temp(name=new_sym.name))
        new_mj = mj.model_copy(update={'conds': new_conds})
        block.stms[-1] = new_mj
