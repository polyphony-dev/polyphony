from .block import Block
from .env import env
from .ir import *
from .usedef import UseDefDetector


class CFGChecker(object):
    def process(self, scope):
        if scope.is_namespace() or scope.is_class():
            return
        if env.compile_phase > env.PHASE_1:
            UseDefDetector().process(scope)
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
            assert stm.is_a(IRStm)
            assert stm.block is blk

    def _check_preds(self, blk):
        if blk is self.scope.entry_block:
            assert len(blk.preds) == 0
            return
        assert len(blk.preds) > 0
        for p in blk.preds:
            assert blk in p.succs

        for p in blk.preds_loop:
            assert p in blk.preds
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
                assert blk.stms[-1].is_a(RET)
            return
        assert blk.stms
        jmp = blk.stms[-1]
        assert jmp.is_a([JUMP, CJUMP, MCJUMP])
        if jmp.is_a(JUMP):
            assert len(blk.succs) == 1
            assert jmp.target is blk.succs[0]
            if jmp.typ == 'L':
                assert len(blk.succs_loop) == 1
                assert jmp.target is blk.succs_loop[0]
        elif jmp.is_a(CJUMP):
            assert len(blk.succs) == 2
            assert len(blk.succs_loop) == 0
            assert jmp.true is blk.succs[0]
            assert jmp.false is blk.succs[1]
        elif jmp.is_a(MCJUMP):
            assert len(blk.succs) > 2
            assert len(blk.succs_loop) == 0
            for i, t in enumerate(jmp.targets):
                assert t is blk.succs[i]

    def _check_phi(self, blk):
        pass

    def _check_vars(self, blk):
        syms = self.scope.usedef.get_syms_used_at(blk)
        for sym in syms:
            if sym.scope is self.scope:
                if self._is_undefined_sym(sym):
                    continue
                defblks = self.scope.usedef.get_blks_defining(sym)
                assert defblks, '{} is not defined in this scope'.format(sym)
                diffs = defblks - self.accessibles
                assert not diffs, '{} is defined in an inaccesible block'.format(sym)

    def _is_undefined_sym(self, sym):
                return (sym.is_predefined() or
                        sym.is_param() or sym.is_static() or
                        sym.is_self() or sym.is_return() or
                        sym.typ.is_function() or
                        # TODO:
                        sym.is_inlined() or
                        (sym.is_subobject() and sym.is_flattened()))

    def _check_path_exp(self, blk):
        pass