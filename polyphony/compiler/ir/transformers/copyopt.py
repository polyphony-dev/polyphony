from collections import deque
from ..ir import *
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..scope import Scope
from ..types.type import Type
from ..symbol import Symbol
from ..analysis.usedef import UseDefUpdater
from logging import getLogger
logger = getLogger(__name__)


class CopyOpt(IRVisitor):
    def _new_collector(self, copies: list[MOVE]):
        return CopyCollector(copies)

    def __init__(self):
        super().__init__()

    def _find_old_use(self, scope, ir, qname: tuple[str, ...]):
        return ir.find_vars(qname)

    def process(self, scope):
        self.scope = scope
        copies: list[MOVE] = []
        collector = self._new_collector(copies)
        collector.process(scope)
        worklist = deque(copies)
        while worklist:
            cp = worklist.popleft()
            logger.debug('copy stm ' + str(cp))
            dst_qsym = cast(tuple[Symbol], qualified_symbols(cp.dst, scope))
            defs = list(scope.usedef.get_stms_defining(dst_qsym))
            if len(defs) > 1:
                # dst must be non ssa variables
                copies.remove(cp)
                continue
            src_qsym = cast(tuple[Symbol], qualified_symbols(cast(IRNameExp, cp.src), scope))
            orig = self._find_root_def(src_qsym)
            udupdater = UseDefUpdater(scope)
            replaced = self._replace_copies(scope, udupdater, cp, orig, dst_qsym, copies, worklist)
            if dst_qsym[0].is_free():
                for clos in scope.closures():
                    udupdater = UseDefUpdater(clos)
                    self._replace_copies(clos, udupdater, cp, orig, dst_qsym, copies, worklist)
                if replaced:
                    src_qsym[0].add_tag('free')
        for cp in copies:
            if cp in cp.block.stms:
                # TODO: Copy propagation of module parameter should be supported
                if cp.dst.is_a(ATTR) and qualified_symbols(cp.dst, self.scope)[-2].typ.scope.is_module() and scope.is_ctor():
                    continue
                if cp.is_a(CMOVE) and not cp.dst.symbol.is_temp():
                    continue
                cp.block.stms.remove(cp)

    def _replace_copies(self, scope: Scope, udupdater: UseDefUpdater, copy_stm: MOVE, orig: IR|None, target: tuple[Symbol], copies: list[MOVE], worklist):
        uses = sorted(list(scope.usedef.get_stms_using(target)), key=lambda u: u.loc)
        for u in uses:
            qname = tuple(map(lambda s: s.name, target))
            olds = self._find_old_use(scope, u, qname)
            for old in olds:
                if orig:
                    new = orig.clone()
                else:
                    new = copy_stm.src.clone()
                # TODO: we need the bit width propagation
                logger.debug('replace FROM ' + str(u))
                udupdater.update(u, None)
                u.replace(old, new)
                if (isinstance(u, MOVE) and
                        isinstance(u.dst, IRVariable) and
                        isinstance(u.src, IRVariable) and
                        u.src.qualified_name == u.dst.qualified_name):
                    logger.debug('replace result is dead stm ' + str(u))
                    u.block.stms.remove(u)
                    continue
                logger.debug('replace TO ' + str(u))
                udupdater.update(None, u)
            if u.is_a(PHIBase):
                # TODO: check
                qsyms = [qualified_symbols(arg, self.scope) for arg in u.args
                        if isinstance(arg, IRVariable) and arg.name != u.var.name]
                if qsyms:
                    if len(u.args) == len(qsyms) and all(qsyms[0] == s for s in qsyms):
                        src = u.args[0]
                    elif len(qsyms) == 1 and len([arg for arg in u.args if isinstance(arg, IRVariable)]) > 1:
                        for arg in u.args:
                            if isinstance(arg, IRVariable) and qualified_symbols(arg, self.scope) == qsyms[0]:
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
                    udupdater.update(u, mv)
                    if isinstance(mv.src, IRVariable):
                        worklist.append(mv)
                        copies.append(mv)
        return len(uses) > 0

    def _find_root_def(self, qsym: tuple[Symbol]) -> IR|None:
        defs = list(self.scope.usedef.get_stms_defining(qsym))
        if len(defs) != 1:
            return None
        d = defs[0]
        if d.is_a(MOVE):
            dst_sym = qualified_symbols(d.dst, self.scope)[-1]
            assert isinstance(dst_sym, Symbol)
            dst_t = dst_sym.typ
            if d.src.is_a(TEMP):
                src_qsym = qualified_symbols(d.src, self.scope)
                src_sym = src_qsym[-1]
                assert isinstance(src_sym, Symbol)
                if src_sym.is_param():
                    return None
                src_t = src_sym.typ
                if src_t != dst_t:
                    return None
                orig = self._find_root_def(src_qsym)
                if orig:
                    return orig
                else:
                    return d.src
            elif d.src.is_a(ATTR):
                src_qsym = qualified_symbols(d.src, self.scope)
                src_sym = src_qsym[-1]
                assert isinstance(src_sym, Symbol)
                src_t = src_sym.typ
                if src_t != dst_t:
                    return None
                orig = self._find_root_def(src_qsym)
                if orig:
                    return orig
                else:
                    return d.src
        return None


class CopyCollector(IRVisitor):
    def __init__(self, copies: list[MOVE]):
        self.copies: list[MOVE] = copies

    def visit_CMOVE(self, ir):
        return

    def visit_MOVE(self, ir):
        dst_sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(dst_sym, Symbol)
        dst_t = dst_sym.typ
        if dst_sym.is_return():
            return
        if dst_sym.is_register():
            return
        if dst_sym.is_field():
            return
        if dst_sym.is_free():
            return
        if ir.src.is_a(TEMP):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            src_t = src_sym.typ
            if src_sym.is_param():  # or ir.src.sym.typ.is_list():
                return
            # compare without explicit attribute
            if src_t.clone(explicit=True) != dst_t.clone(explicit=True):
                return
            self.copies.append(ir)
        elif ir.src.is_a(ATTR):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            src_t = src_sym.typ
            if src_t.is_object() and src_t.scope.is_port():
                self.copies.append(ir)


class ObjCopyOpt(CopyOpt):
    def _new_collector(self, copies: list[MOVE]):
        return ObjCopyCollector(copies)

    def __init__(self):
        super().__init__()

    def _find_old_use(self, scope, ir, qname: tuple[str, ...]):
        vars = []

        def find_vars_rec(ir, qname: tuple[str, ...], vars: list[IR]):
            if isinstance(ir, IR):
                if ir.is_a(ATTR):
                    attr = cast(ATTR, ir)
                    if attr.qualified_name == qname:
                        vars.append(attr)
                    find_vars_rec(attr.exp, qname, vars)
                elif ir.is_a(TEMP) and len(qname) == 1:
                    temp = cast(TEMP, ir)
                    sym = scope.find_sym(temp.name)
                    assert sym
                    sym_t = sym.typ
                    if sym_t.is_object():
                        if temp.name == qname[0]:
                            vars.append(ir)
                    elif sym_t.is_seq():
                        if temp.name == qname[0]:
                            vars.append(ir)
                else:
                    for k, v in ir.__dict__.items():
                        find_vars_rec(v, qname, vars)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_vars_rec(elm, qname, vars)
        find_vars_rec(ir, qname, vars)
        return vars


class ObjCopyCollector(IRVisitor):
    def __init__(self, copies):
        self.copies = copies

    def _is_alias_def(self, mov):
        if not mov.is_a(MOVE):
            return False
        if not mov.src.is_a(IRVariable):
            return False
        if not mov.dst.is_a(IRVariable):
            return False
        if mov.dst.is_a(ATTR):
            receiver = qualified_symbols(mov.dst.exp, self.scope)[-1]
            assert isinstance(receiver, Symbol)
            receiver_t = receiver.typ
            if receiver_t.is_object() and receiver_t.scope.is_module():
                return False
        #if mov.src.symbol.is_induction() or mov.dst.symbol.is_induction():
        #    return False
        src_sym = qualified_symbols(mov.src, self.scope)[-1]
        dst_sym = qualified_symbols(mov.dst, self.scope)[-1]
        assert isinstance(src_sym, Symbol)
        assert isinstance(dst_sym, Symbol)
        src_t = src_sym.typ
        dst_t = dst_sym.typ
        if src_t.is_object() and dst_t.is_object():
            return True
        if src_t.is_seq() and dst_t.is_seq():
            return True
        return False

    def visit_MOVE(self, ir):
        if not self._is_alias_def(ir):
            return
        src_sym = qualified_symbols(ir.src, self.scope)[-1]
        assert isinstance(src_sym, Symbol)
        if src_sym.is_param():
            return
        self.copies.append(ir)
