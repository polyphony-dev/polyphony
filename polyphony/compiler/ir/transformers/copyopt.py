﻿from collections import deque
from ..ir import *
from ..irvisitor import IRVisitor
from ..type import Type
from ..analysis.usedef import UseDefUpdater
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
        self.udupdater = UseDefUpdater(scope)
        copies = []
        collector = self._new_collector(copies)
        collector.process(scope)
        worklist = deque(copies)
        while worklist:
            cp = worklist.popleft()
            logger.debug('copy stm ' + str(cp))
            dst_qsym = cp.dst.qualified_symbol
            defs = list(scope.usedef.get_stms_defining(dst_qsym))
            if len(defs) > 1:
                # dst must be non ssa variables
                copies.remove(cp)
                continue
            orig = self._find_root_def(cp.src.qualified_symbol)
            self._replace_copies(scope, cp, orig, dst_qsym, copies, worklist)
            if dst_qsym[0].is_free():
                for clos in scope.closures:
                    self._replace_copies(clos, cp, orig, dst_qsym, copies, worklist)
        for cp in copies:
            if cp in cp.block.stms:
                # TODO: Copy propagation of module parameter should be supported
                if cp.dst.is_a(ATTR) and cp.dst.tail().typ.get_scope().is_module() and scope.is_ctor():
                    continue
                if cp.is_a(CMOVE) and not cp.dst.symbol.is_temp():
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
                new.symbol.typ = old.symbol.typ
                logger.debug('replace FROM ' + str(u))
                self.udupdater.update(u, None)
                u.replace(old, new)
                logger.debug('replace TO ' + str(u))
                self.udupdater.update(None, u)
            if u.is_a(PHIBase):
                syms = [arg.qualified_symbol for arg in u.args
                        if arg.is_a([TEMP, ATTR]) and arg.symbol is not u.var.symbol]
                if syms:
                    if len(u.args) == len(syms) and all(syms[0] == s for s in syms):
                        src = u.args[0]
                    elif len(syms) == 1 and len([arg for arg in u.args if arg.is_a([TEMP, ATTR])]) > 1:
                        for arg in u.args:
                            if arg.is_a([TEMP, ATTR]) and arg.qualified_symbol == syms[0]:
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
                    self.udupdater.update(u, mv)
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
                scope.add_free_sym(src.symbol)
            else:
                assert False

    def _find_root_def(self, qsym) -> IR:
        defs = list(self.scope.usedef.get_stms_defining(qsym))
        if len(defs) != 1:
            return None
        d = defs[0]
        if d.is_a(MOVE):
            dst_t = d.dst.symbol.typ
            if d.src.is_a(TEMP):
                if d.src.symbol.is_param():
                    return None
                src_t = d.src.symbol.typ
                if src_t != dst_t:
                    return None
                orig = self._find_root_def(d.src.qualified_symbol)
                if orig:
                    return orig
                else:
                    return d.src
            elif d.src.is_a(ATTR):
                src_t = d.src.symbol.typ
                if src_t != dst_t:
                    return None
                orig = self._find_root_def(d.src.qualified_symbol)
                if orig:
                    return orig
                else:
                    return d.src
        return None


class CopyCollector(IRVisitor):
    def __init__(self, copies):
        self.copies = copies

    def visit_CMOVE(self, ir):
        return

    def visit_MOVE(self, ir):
        dst_t = ir.dst.symbol.typ
        if ir.dst.symbol.is_return():
            return
        if ir.dst.symbol.is_register():
            return
        if ir.dst.symbol.is_field():
            return
        if ir.dst.symbol.is_free():
            return
        if ir.src.is_a(TEMP):
            src_t = ir.src.symbol.typ
            if ir.src.symbol.is_param():  # or ir.src.sym.typ.is_list():
                return
            if src_t != dst_t:
                return
            self.copies.append(ir)
        elif ir.src.is_a(ATTR):
            src_t = ir.src.symbol.typ
            if src_t.is_object() and src_t.get_scope().is_port():
                self.copies.append(ir)


class ObjCopyOpt(CopyOpt):
    def _new_collector(self, copies):
        return ObjCopyCollector(copies)

    def __init__(self):
        super().__init__()

    def _find_old_use(self, ir, qsym):
        vars = []

        def find_vars_rec(ir, qsym, vars):
            if isinstance(ir, IR):
                if ir.is_a(ATTR):
                    attr_t = ir.symbol.typ
                    if attr_t.is_object():
                        if ir.qualified_symbol == qsym:
                            vars.append(ir)
                    elif attr_t.is_seq():
                        if ir.qualified_symbol == qsym:
                            vars.append(ir)
                    elif ir.exp.qualified_symbol == qsym:
                        vars.append(ir.exp)
                elif ir.is_a(TEMP) and len(qsym) == 1:
                    sym_t = ir.symbol.typ
                    if sym_t.is_object():
                        if ir.symbol == qsym[0]:
                            vars.append(ir)
                    elif sym_t.is_seq():
                        if ir.symbol == qsym[0]:
                            vars.append(ir)
                else:
                    for k, v in ir.__dict__.items():
                        find_vars_rec(v, qsym, vars)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_vars_rec(elm, qsym, vars)
        find_vars_rec(ir, qsym, vars)
        return vars


class ObjCopyCollector(IRVisitor):
    def __init__(self, copies):
        self.copies = copies

    def _is_alias_def(self, mov):
        if not mov.is_a(MOVE):
            return False
        if not mov.src.is_a([TEMP, ATTR]):
            return False
        if not mov.dst.is_a([TEMP, ATTR]):
            return False
        if mov.dst.is_a(ATTR):
            tail_t = mov.dst.tail().typ
            if tail_t.is_object() and tail_t.get_scope().is_module():
                return False
        #if mov.src.symbol.is_induction() or mov.dst.symbol.is_induction():
        #    return False
        src_t = mov.src.symbol.typ
        dst_t = mov.dst.symbol.typ
        if src_t.is_object() and dst_t.is_object():
            return True
        if src_t.is_seq() and dst_t.is_seq():
            return True
        return False

    def visit_MOVE(self, ir):
        if not self._is_alias_def(ir):
            return
        if ir.src.symbol.is_param():
            return
        self.copies.append(ir)
