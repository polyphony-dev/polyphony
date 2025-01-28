from ..ir import *
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..symbol import Symbol
from logging import getLogger
logger = getLogger(__name__)


class AliasVarDetector(IRVisitor):
    def process(self, scope):
        self.usedef = scope.usedef
        self.removes = []
        super().process(scope)

    def visit_CMOVE(self, ir):
        assert ir.dst.is_a(IRVariable)
        sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym.is_condition() or self.scope.is_comb():
            logger.debug(f'{sym} is alias')
            sym.add_tag('alias')

    def visit_MOVE(self, ir):
        assert ir.dst.is_a(IRVariable)
        sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(sym, Symbol)
        sched = self.current_stm.block.synth_params['scheduling']
        if sym.is_condition() or self.scope.is_comb():
            sym.add_tag('alias')
            logger.debug(f'{sym} is alias')
            return
        if sym.is_register() or sym.is_return() or sym.typ.is_port():
            return
        if sym.is_field():
            if self.scope.is_worker():
                module = self.scope.worker_owner
            else:
                # TODO:
                module = self.scope.parent
            if sym.typ.is_object():
                return
            qsym = qualified_symbols(ir.dst, self.scope)
            defstms = module.field_usedef.get_def_stms(qsym)
            if len(defstms) == 1:
                sym.add_tag('alias')
                logger.debug(f'{sym} is alias')
            return
        if sym.typ.is_tuple() and sched == 'timed':
            sym.add_tag('alias')
            logger.debug(f'{sym} is alias')
            return
        if ir.src.is_a(IRVariable):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            if self.scope.is_ctor() and self.scope.parent.is_module():
                pass
            elif src_sym.is_param() or src_sym.typ.is_port():
                return
        elif ir.src.is_a(CALL):
            callee_scope = ir.src.get_callee_scope(self.scope)
            # callee_scope = ir.src.callee_scope
            func_name = ir.src.name
            if callee_scope.is_predicate():
                return
            elif callee_scope.is_method() and callee_scope.parent.is_port():
                if func_name in ('rd', 'edge'):
                    pass
                else:
                    return
            elif callee_scope.is_method() and callee_scope.parent.name.startswith('polyphony.Net'):
                if func_name in ('rd'):
                    pass
                else:
                    return
            else:
                return
        elif ir.src.is_a(NEW):
            return
        elif ir.src.is_a(SYSCALL):
            if ir.src.name == '$new':
                return
        elif ir.src.is_a(MREF):
            if sched == 'timed':
                 pass
            else:
                mem_sym = qualified_symbols(ir.src.mem, self.scope)[-1]
                assert isinstance(mem_sym, Symbol)
                stms = self.usedef.get_stms_using(mem_sym)
                for stm in stms:
                    if stm.is_a(EXPR) and stm.exp.is_a(MSTORE) and stm.exp.mem == ir.src.mem:
                        return
        elif ir.src.is_a(ARRAY):
            return
        stms = self.usedef.get_stms_defining(sym)
        if len(stms) > 1:
            return
        stms = self.usedef.get_stms_using(sym)
        for stm in stms:
            if sched != 'pipeline' and stm.block.synth_params['scheduling'] == 'pipeline':
                return
            if sched != 'parallel' and stm.block.synth_params['scheduling'] == 'parallel':
                return
        logger.debug(f'{sym} is alias')
        sym.add_tag('alias')

    def visit_PHI(self, ir):
        sym = qualified_symbols(ir.var, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym.is_condition() or self.scope.is_comb():
            sym.add_tag('alias')
            return
        if sym.is_return() or sym.typ.is_port():
            return
        if sym.typ.is_seq():
            return
        arg_syms = []
        for a in ir.args:
            if a.is_a(TEMP):
                arg_syms.append(qualified_symbols(a, self.scope)[-1])
        if any([sym is asym for asym in arg_syms]):
            return
        sym.add_tag('alias')

    def visit_UPHI(self, ir):
        sym = qualified_symbols(ir.var, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym.is_condition() or self.scope.is_comb():
            sym.add_tag('alias')
            return
        if sym.is_return() or sym.typ.is_port():
            return
        if sym.typ.is_seq():
            return
        arg_syms = []
        for a in ir.args:
            if a.is_a(TEMP):
                arg_syms.append(qualified_symbols(a, self.scope)[-1])
        if any([sym is asym for asym in arg_syms]):
            return
        sym.add_tag('alias')
