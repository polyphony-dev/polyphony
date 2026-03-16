"""AliasVarDetector using new IR (ir.py).

Tags variables that can be aliased (wires instead of registers).
This is an analysis pass - reads IR and tags symbols.
"""
from collections import deque
from ..ir import (
    IrVariable, Temp, Attr, Const,
    Move, CMove, Expr, Call, SysCall, New,
    MRef, MStore, Array, Phi, UPhi,
)
from ..ir_visitor import IrVisitor
from ..ir_helper import qualified_symbols
from ..symbol import Symbol
from .usedef import NewUseDefDetector
from .fieldusedef import FieldUseDef
from logging import getLogger
logger = getLogger(__name__)


def _is_clksleep(stm):
    """Check if stm is a clksleep call (excludes wait_until and wait_*)."""
    return (isinstance(stm, Expr) and isinstance(stm.exp, SysCall) and
            stm.exp.name == 'polyphony.timing.clksleep')


class NewAliasVarDetector(IrVisitor):
    """Tag variables that can be aliased (wires instead of registers)."""

    def process(self, scope):
        self.usedef = NewUseDefDetector().process(scope)
        self.removes = []
        super().process(scope)

    def _has_clksleep_between(self, def_stm, use_stm):
        """Check if there is a clksleep between def_stm and use_stm."""
        def_blk = def_stm.block
        use_blk = use_stm.block
        if def_blk is use_blk:
            stms = def_blk.stms
            in_range = False
            for stm in stms:
                if stm is def_stm:
                    in_range = True
                    continue
                if stm is use_stm:
                    return False
                if in_range and _is_clksleep(stm):
                    return True
            return False
        # Different blocks: check if any CFG path from def_blk to use_blk contains a clksleep
        stms = def_blk.stms
        found_def = False
        for stm in stms:
            if stm is def_stm:
                found_def = True
                continue
            if found_def and _is_clksleep(stm):
                return True
        # BFS from def_blk to use_blk
        visited = set()
        queue = deque(def_blk.succs)
        while queue:
            blk = queue.popleft()
            if blk in visited:
                continue
            visited.add(blk)
            if blk is use_blk:
                for stm in blk.stms:
                    if stm is use_stm:
                        break
                    if _is_clksleep(stm):
                        return True
                return False
            for stm in blk.stms:
                if _is_clksleep(stm):
                    return True
            for succ in blk.succs:
                if succ not in visited:
                    queue.append(succ)
        return False

    def visit_CMove(self, ir):
        assert isinstance(ir.dst, IrVariable)
        sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym.is_condition() or self.scope.is_comb():
            logger.debug(f'{sym} is alias')
            sym.add_tag('alias')

    def visit_Move(self, ir):
        assert isinstance(ir.dst, IrVariable)
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
                module = self.scope.parent
                while module is not None and not module.is_module():
                    module = module.parent
            if sym.typ.is_object():
                return
            if module is None:
                return
            field_usedef = FieldUseDef().process(module)
            qsym = qualified_symbols(ir.dst, self.scope)
            defstms = field_usedef.get_def_stms(qsym)
            if len(defstms) == 1:
                sym.add_tag('alias')
                logger.debug(f'{sym} is alias')
            return
        if sym.typ.is_tuple() and sched == 'timed':
            sym.add_tag('alias')
            logger.debug(f'{sym} is alias')
            return
        if isinstance(ir.src, IrVariable):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            if self.scope.is_ctor() and self.scope.parent.is_module():
                pass
            elif src_sym.is_param() or src_sym.typ.is_port():
                return
        elif isinstance(ir.src, Call):
            callee_scope = self._get_callee_scope(ir.src)
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
        elif isinstance(ir.src, New):
            return
        elif isinstance(ir.src, SysCall):
            if ir.src.name == '$new':
                return
        elif isinstance(ir.src, MRef):
            if sched == 'timed':
                pass
            else:
                mem_sym = qualified_symbols(ir.src.mem, self.scope)[-1]
                assert isinstance(mem_sym, Symbol)
                stms = self.usedef.get_stms_using(mem_sym)
                for stm in stms:
                    if isinstance(stm, Expr) and isinstance(stm.exp, MStore) and stm.exp.mem == ir.src.mem:
                        return
        elif isinstance(ir.src, Array):
            return
        def_stms = self.usedef.get_stms_defining(sym)
        if len(def_stms) > 1:
            return
        use_stms = self.usedef.get_stms_using(sym)
        if sched == 'timed' and def_stms:
            def_stm = next(iter(def_stms))
            for use_stm in use_stms:
                if self._has_clksleep_between(def_stm, use_stm):
                    logger.debug(f'{sym} crosses clksleep, keeping as reg')
                    return
        for stm in use_stms:
            if sched != 'pipeline' and stm.block.synth_params['scheduling'] == 'pipeline':
                return
            if sched != 'parallel' and stm.block.synth_params['scheduling'] == 'parallel':
                return
        logger.debug(f'{sym} is alias')
        sym.add_tag('alias')

    def visit_Phi(self, ir):
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
            if isinstance(a, Temp):
                arg_syms.append(qualified_symbols(a, self.scope)[-1])
        if any([sym is asym for asym in arg_syms]):
            return
        sym.add_tag('alias')

    def visit_UPhi(self, ir):
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
            if isinstance(a, Temp):
                arg_syms.append(qualified_symbols(a, self.scope)[-1])
        if any([sym is asym for asym in arg_syms]):
            return
        sym.add_tag('alias')

    def _get_callee_scope(self, call):
        """Get callee scope from a Call node (mirrors old IR get_callee_scope)."""
        qsyms = qualified_symbols(call.func, self.scope)
        symbol = qsyms[-1]
        assert isinstance(symbol, Symbol)
        func_t = symbol.typ
        assert func_t.has_scope()
        return func_t.scope
