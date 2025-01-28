from ..ir import *
from ..irhelper import qualified_symbols
from ..symbol import Symbol
from logging import getLogger
logger = getLogger(__name__)


class DeadCodeEliminator(object):
    def process(self, scope):
        if scope.is_namespace() or scope.is_class():
            return
        usedef = scope.usedef
        for blk in scope.traverse_blocks():
            dead_stms = []
            for stm in blk.stms:
                if stm.is_a([MOVE, PHIBase]):
                    if stm.is_a(MOVE) and stm.src.is_a(IRCallable):
                        continue
                    if stm.is_a(MOVE) and stm.src.is_a(IRVariable):
                        src_sym = qualified_symbols(stm.src, scope)[-1]
                        assert isinstance(src_sym, Symbol)
                    else:
                        src_sym = None
                    if src_sym and src_sym.is_param():
                        continue
                    defvars = usedef.get_vars_defined_at(stm)
                    for var in defvars:
                        if not var.is_a(TEMP):
                            break
                        var_sym = scope.find_sym(var.name)
                        assert var_sym
                        if var_sym.is_free():
                            break
                        if stm.block.path_exp.is_a(IRVariable):
                            path_sym = qualified_symbols(stm.block.path_exp, scope)[-1]
                            assert isinstance(path_sym, Symbol)
                        else:
                            path_sym = None
                        if path_sym and path_sym is var_sym:
                            break
                        uses = usedef.get_stms_using(var_sym)
                        if uses:
                            break
                    else:
                        dead_stms.append(stm)
                elif stm.is_a(EXPR):
                    if not stm.exp.is_a([CALL, SYSCALL, MSTORE]):
                        dead_stms.append(stm)
            for stm in dead_stms:
                blk.stms.remove(stm)
                logger.debug('removed dead code: ' + str(stm))
