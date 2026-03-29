"""DeadCodeEliminator using new IR (ir.py)."""
from ..ir import (
    Move, Expr, Temp, IrCallable, IrVariable, Call, SysCall, MStore,
    Phi, UPhi, LPhi,
)
from ..irhelper import qualified_symbols
from ..symbol import Symbol
from ..analysis.usedef import UseDefDetector
from logging import getLogger
logger = getLogger(__name__)


# Phi base classes in new IR
_PHI_TYPES = (Phi, UPhi, LPhi)


class DeadCodeEliminator(object):
    def process(self, scope):
        if scope.is_namespace() or scope.is_class():
            return
        usedef = UseDefDetector().process(scope)
        for blk in scope.traverse_blocks():
            dead_stms = []
            for stm in blk.stms:
                if isinstance(stm, (Move, *_PHI_TYPES)):
                    if isinstance(stm, Move) and isinstance(stm.src, IrCallable):
                        continue
                    if isinstance(stm, Move) and isinstance(stm.src, IrVariable):
                        src_sym = qualified_symbols(stm.src, scope)[-1]
                        assert isinstance(src_sym, Symbol)
                    else:
                        src_sym = None
                    if src_sym and src_sym.is_param():
                        continue
                    defvars = usedef.get_vars_defined_at(stm)
                    for var in defvars:
                        if not isinstance(var, Temp):
                            break
                        var_sym = scope.find_sym(var.name)
                        assert var_sym
                        if var_sym.is_free():
                            break
                        path_exp = blk.path_exp
                        if isinstance(path_exp, IrVariable):
                            path_sym = qualified_symbols(path_exp, scope)[-1]
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
                elif isinstance(stm, Expr):
                    if not isinstance(stm.exp, (Call, SysCall, MStore)):
                        dead_stms.append(stm)
            for stm in dead_stms:
                blk.stms.remove(stm)
                logger.debug('removed dead code: ' + str(stm))
