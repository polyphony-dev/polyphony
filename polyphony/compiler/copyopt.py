from .ir import *
from .irvisitor import IRVisitor
from .type import Type
from logging import getLogger
logger = getLogger(__name__)

class CopyOpt(IRVisitor):
    def process(self, scope):
        self.scope = scope
        copies = []
        collector = CopyCollector(copies)
        collector.process(scope)

        for cp in copies:
            #logger.debug(str(scope))
            assert cp.dst.is_a(TEMP)
            uses = list(scope.usedef.get_use_stms_by_sym(cp.dst.sym))
            orig = self._get_original(cp.src.sym)
            for u in uses:
                olds = u.find_vars(cp.dst.sym)
                assert olds
                for old in olds:
                    if orig:
                        new = orig.clone()
                    else:
                        new = cp.src.clone()
                    logger.debug('replace FROM ' + str(u))
                    u.replace(old, new)
                    logger.debug('replace TO ' + str(u))
                    scope.usedef.remove_use(old, u)
                    scope.usedef.add_use(new, u)
        for cp in copies:
            if cp in cp.block.stms:
                cp.block.stms.remove(cp)

    def _get_original(self, sym) -> IR:
        defs = list(self.scope.usedef.get_def_stms_by_sym(sym))
        if not defs:
            return
        assert len(defs) == 1
        d = defs[0]
        if d.is_a(MOVE):
            if d.src.is_a(TEMP):
                orig = self._get_original(d.src.sym)
                if orig:
                    return orig
                else:
                    d.src
            elif d.src.is_a(ATTR):
                return d.src
        return None

class CopyCollector(IRVisitor):
    def __init__(self, copies):
        self.copies = copies

    def visit_MOVE(self, ir):
        if not ir.dst.is_a(TEMP):
            return
        if ir.dst.sym.is_return():
            return
        if ir.src.is_a(TEMP):
            if ir.src.sym.is_param() and Type.is_list(ir.src.sym.typ):
                return
            self.copies.append(ir)


