from .ir import *
from .irvisitor import IRVisitor
from .type import Type
from logging import getLogger
logger = getLogger(__name__)

class CopyOpt(IRVisitor):
    def _new_collector(self, copies):
        return CopyCollector(copies)

    def __init__(self):
        super().__init__()

    def _find_old_use(self, ir, qsym):
        return ir.find_vars(qsym)

    def process(self, scope):
        self.scope = scope
        copies = []
        collector = self._new_collector(copies)
        collector.process(scope)
        for cp in copies:
            uses = list(scope.usedef.get_use_stms_by_qsym(cp.dst.qualified_symbol()))
            orig = self._find_root_def(cp.src.qualified_symbol())
            for u in uses:
                olds = self._find_old_use(u, cp.dst.qualified_symbol())
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

    def _find_root_def(self, qsym) -> IR:
        defs = list(self.scope.usedef.get_def_stms_by_qsym(qsym))
        if not defs:
            return None
        assert len(defs) == 1
        d = defs[0]
        if d.is_a(MOVE):
            if d.src.is_a(TEMP):
                if d.src.symbol().is_param():
                    return None
                orig = self._find_root_def(d.src.qualified_symbol())
                if orig:
                    return orig
                else:
                    return d.src
            elif d.src.is_a(ATTR):
                orig = self._find_root_def(d.src.qualified_symbol())
                if orig:
                    return orig
                else:
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
            if ir.src.sym.is_param():# or Type.is_list(ir.src.sym.typ):
                return
            self.copies.append(ir)


