from collections import deque
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
        worklist = deque(copies)
        while worklist:
            cp = worklist.popleft()
            logger.debug('copy stm ' + str(cp))
            dst_qsym = cp.dst.qualified_symbol()
            uses = list(scope.usedef.get_stms_using(dst_qsym))
            orig = self._find_root_def(cp.src.qualified_symbol())
            for u in uses:
                olds = self._find_old_use(u, dst_qsym)
                for old in olds:
                    if orig:
                        new = orig.clone()
                    else:
                        new = cp.src.clone()
                    # TODO: we need the bit width propagation
                    if not new.symbol().typ.is_freezed():
                        new.symbol().set_type(old.symbol().typ.clone())
                    logger.debug('replace FROM ' + str(u))
                    u.replace(old, new)
                    logger.debug('replace TO ' + str(u))
                    scope.usedef.remove_use(old, u)
                    scope.usedef.add_use(new, u)
                if u.is_a(PHIBase):
                    syms = [arg.qualified_symbol() for arg in u.args
                            if arg.is_a([TEMP, ATTR]) and arg.symbol() is not u.var.symbol()]
                    if syms:
                        if len(u.args) == len(syms) and all(syms[0] == s for s in syms):
                            src = u.args[0]
                        elif len(syms) == 1 and len([arg for arg in u.args if arg.is_a([TEMP, ATTR])]) > 1:
                            for arg in u.args:
                                if arg.is_a([TEMP, ATTR]) and arg.qualified_symbol() == syms[0]:
                                    src = arg
                                    break
                            else:
                                assert False
                        else:
                            continue
                        mv = MOVE(u.var, src)
                        idx = u.block.stms.index(u)
                        u.block.stms[idx] = mv
                        mv.block = u.block
                        mv.lineno = u.lineno
                        scope.usedef.remove_stm(u)
                        scope.usedef.add_var_def(mv.dst, mv)
                        scope.usedef.add_use(mv.src, mv)
                        if mv.src.is_a([TEMP, ATTR]):
                            worklist.append(mv)
                            copies.append(mv)

        for cp in copies:
            if cp in cp.block.stms:
                # TODO: Copy propagation of module parameter should be supported
                if cp.dst.is_a(ATTR) and cp.dst.tail().typ.get_scope().is_module() and scope.is_ctor():
                    continue
                cp.block.stms.remove(cp)

    def _find_root_def(self, qsym) -> IR:
        defs = list(self.scope.usedef.get_stms_defining(qsym))
        if len(defs) != 1:
            return None
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
        if ir.dst.symbol().is_return():
            return
        if ir.src.is_a(TEMP):
            if ir.src.sym.is_param():  # or ir.src.sym.typ.is_list():
                return
            if not Type.is_strict_same(ir.dst.symbol().typ, ir.src.sym.typ):
                return
            self.copies.append(ir)
        elif ir.src.is_a(ATTR):
            typ = ir.src.symbol().typ
            if typ.is_object() and typ.get_scope().is_port():
                self.copies.append(ir)
