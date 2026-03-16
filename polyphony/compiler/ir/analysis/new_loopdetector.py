"""Loop analysis using new IR (ir_model.py)."""
from ..ir_model import CJump, Temp, Const, RelOp, LPhi
from ..ir_helper import qualified_symbols
from ..symbol import Symbol
from ..analysis.new_usedef import NewUseDefDetector
from ..analysis.loopdetector import Loop
from logging import getLogger
logger = getLogger(__name__)


class NewLoopInfoSetter(object):
    def process(self, scope):
        self.scope = scope
        self.usedef = NewUseDefDetector().process(scope)
        for loop in self.scope.child_regions(self.scope.top_region()):
            self._set_loop_info_rec(loop)

    def _set_loop_info_rec(self, loop):
        self._set_loop_info(loop)
        for child in self.scope.child_regions(loop):
            self._set_loop_info_rec(child)

    def _set_loop_info(self, loop):
        assert isinstance(loop, Loop)
        if loop.counter:
            return
        if not loop.head.ir_stms:
            return
        cjump = loop.head.ir_stms[-1]
        if not isinstance(cjump, CJump):
            return
        cond_var = cjump.exp
        cond_sym = qualified_symbols(cond_var, self.scope)[-1]
        loop.cond = cond_sym
        assert isinstance(cond_var, Temp)
        defs = self.usedef.get_stms_defining(cond_sym)
        assert len(defs) == 1
        cond_stm = list(defs)[0]
        from ..ir_model import Move
        assert isinstance(cond_stm, Move)
        if not isinstance(cond_stm.src, RelOp):
            return
        loop_relexp = cond_stm.src

        if isinstance(loop_relexp.left, Temp) and (left_sym := self.scope.find_sym(loop_relexp.left.name)) and left_sym.is_induction():
            assert isinstance(loop_relexp.right, (Const, Temp))
            loop.counter = left_sym
            loop.counter.add_tag('loop_counter')
        elif isinstance(loop_relexp.right, Temp) and (right_sym := self.scope.find_sym(loop_relexp.right.name)) and right_sym.is_induction():
            assert isinstance(loop_relexp.left, (Const, Temp))
            loop.counter = right_sym
            loop.counter.add_tag('loop_counter')
        else:
            lphis = loop.head.collect_ir_stms([LPhi])
            for lphi in lphis:
                var_sym = qualified_symbols(lphi.var, self.scope)[-1]
                assert isinstance(var_sym, Symbol)
                if var_sym.is_loop_counter():
                    loop.counter = var_sym
                    break
            else:
                return
        defs = self.usedef.get_stms_defining(loop.counter)
        assert len(defs) == 1
        counter_def = list(defs)[0]
        assert len(counter_def.args) == 2
        loop.init = counter_def.args[0]
        loop.update = counter_def.args[1]
        loop.exits = []
        for blk in loop.inner_blocks:
            for s in blk.succs:
                if s not in loop.inner_blocks:
                    loop.exits.append(s)
        assert loop.update
        assert loop.init
        logger.debug(loop)
