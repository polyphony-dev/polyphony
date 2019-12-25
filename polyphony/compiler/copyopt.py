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
            defs = list(scope.usedef.get_stms_defining(dst_qsym))
            if len(defs) > 1:
                # dst must be non ssa variables
                continue
            orig = self._find_root_def(cp.src.qualified_symbol())
            self._replace_copies(scope, cp, orig, dst_qsym, copies, worklist)
            if dst_qsym[0].is_free():
                for clos in scope.closures:
                    self._replace_copies(clos, cp, orig, dst_qsym, copies, worklist)
        for cp in copies:
            if cp in cp.block.stms:
                # TODO: Copy propagation of module parameter should be supported
                if cp.dst.is_a(ATTR) and cp.dst.tail().typ.get_scope().is_module() and scope.is_ctor():
                    continue
                if cp.is_a(CMOVE) and not cp.dst.symbol().is_temp():
                    continue
                cp.block.stms.remove(cp)

    def _replace_copies(self, scope, copy_stm, orig, target, copies, worklist):
        uses = list(scope.usedef.get_stms_using(target))
        for u in uses:
            olds = self._find_old_use(u, target)
            for old in olds:
                if orig:
                    new = orig.clone()
                else:
                    new = copy_stm.src.clone()
                # TODO: we need the bit width propagation
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
                    scope.usedef.remove_stm(u)
                    scope.usedef.add_var_def(mv.dst, mv)
                    scope.usedef.add_use(mv.src, mv)
                    if mv.src.is_a([TEMP, ATTR]):
                        worklist.append(mv)
                        copies.append(mv)
        # Deal with 'free' attribute
        if target[0].is_free() and target[0] in scope.free_symbols:
            scope.free_symbols.remove(target[0])
            if orig:
                src = orig
            else:
                src = copy_stm.src
            if src.is_a(ATTR):
                scope.add_free_sym(src.head())
            elif src.is_a(TEMP):
                scope.add_free_sym(src.symbol())
            else:
                assert False

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
        if ir.dst.symbol().is_register():
            return
        if ir.dst.symbol().is_field():
            return
        if ir.dst.symbol().is_free():
            return
        if ir.src.is_a(TEMP):
            if ir.src.sym.is_param():  # or ir.src.sym.typ.is_list():
                return
            if not ir.dst.symbol().typ == ir.src.sym.typ:
                return
            self.copies.append(ir)
        elif ir.src.is_a(ATTR):
            typ = ir.src.symbol().typ
            if typ.is_object() and typ.get_scope().is_port():
                self.copies.append(ir)
