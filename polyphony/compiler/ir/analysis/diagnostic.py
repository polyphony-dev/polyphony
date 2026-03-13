from ..block import Block
from ...common.env import env
from ..ir import *
from ..symbol import Symbol
from .usedef import UseDefDetector
from logging import getLogger
logger = getLogger(__name__)


class CFGChecker(object):
    def process(self, scope):
        if scope.is_namespace() or scope.is_class() or scope.is_builtin() or scope.is_lib():
            return
        if env.compile_phase > env.PHASE_1:
            self.usedef = UseDefDetector().process(scope)
        self.scope = scope
        self.accessibles = set()
        for b in self.scope.traverse_blocks():
            self.accessibles.add(b)

        for b in self.scope.traverse_blocks():
            if isinstance(b, Block):
                self._check_blk(b)
            else:
                assert False

    def _check_blk(self, blk):
        self._check_stms(blk)
        self._check_preds(blk)
        self._check_succs(blk)
        self._check_jump(blk)
        if env.compile_phase > env.PHASE_1:
            self._check_vars(blk)
            self._check_path_exp(blk)
            self._check_phi(blk)

    def _check_stms(self, blk):
        for stm in blk.stms:
            assert isinstance(stm, IRStm)
            assert stm.block is blk

    def _check_preds(self, blk):
        if blk is self.scope.entry_block:
            assert len(blk.preds) == 0
            return
        assert len(blk.preds) > 0
        for p in blk.preds:
            assert blk in p.succs

        for p in blk.preds_loop:
            assert p in blk.preds, f"{p.name} not in {blk.name}.preds"
            assert blk in p.succs_loop

    def _check_succs(self, blk):
        if blk is self.scope.exit_block:
            if self.scope.is_worker():
                # when worker has infinite loop, the exit block must be the loop head block
                if blk.succs and blk.preds:
                    assert len(blk.preds_loop)
            else:
                assert len(blk.succs) == 0
            return
        assert len(blk.succs) > 0
        for s in blk.succs:
            assert blk in s.preds

        for s in blk.succs_loop:
            assert s in blk.succs
            assert blk in s.preds_loop

    def _check_jump(self, blk):
        if blk is self.scope.exit_block:
            if self.scope.is_returnable():
                assert blk.stms
                assert isinstance(blk.stms[-1], RET)
            return
        assert blk.stms
        jmp = blk.stms[-1]
        assert isinstance(jmp, (JUMP, CJUMP, MCJUMP))
        if isinstance(jmp, JUMP):
            assert len(blk.succs) == 1
            assert jmp.target is blk.succs[0]
            if jmp.typ == 'L':
                assert len(blk.succs_loop) == 1
                assert jmp.target is blk.succs_loop[0]
        elif isinstance(jmp, CJUMP):
            assert len(blk.succs) == 2
            assert len(blk.succs_loop) == 0
            assert jmp.true is blk.succs[0]
            assert jmp.false is blk.succs[1]
        elif isinstance(jmp, MCJUMP):
            assert len(blk.succs) > 2
            assert len(blk.succs_loop) == 0
            for i, t in enumerate(jmp.targets):
                assert t is blk.succs[i]

    def _check_phi(self, blk):
        pass

    def _check_vars(self, blk):
        syms = self.usedef.get_syms_used_at(blk)
        for sym in syms:
            if sym.scope is self.scope:
                if self._is_undefined_sym(sym):
                    continue
                defblks = self.usedef.get_blks_defining(sym)
                if not defblks:
                    logger.warning('{} is not defined in this scope {}'.format(sym, self.scope.name))
                    continue
                diffs = defblks - self.accessibles
                if diffs:
                    logger.warning('{} is defined in an inaccesible block'.format(sym))

    def _is_undefined_sym(self, sym):
                return (sym.is_predefined() or
                        sym.is_param() or sym.is_static() or
                        sym.is_self() or sym.is_return() or
                        sym.typ.is_function() or
                        sym.typ.is_class() or
                        sym.is_free() or
                        sym.is_imported() or
                        # TODO:
                        sym.is_inlined() or
                        (sym.is_subobject() and sym.is_flattened()) or
                        sym.typ.has_scope() and sym.typ.scope.is_unflatten()
                        )

    def _check_path_exp(self, blk):
        pass
