from collections import deque
from ..ir import *
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..symbol import Symbol
from .usedef import UseDefDetector
from .fieldusedef import FieldUseDef
from logging import getLogger
logger = getLogger(__name__)


def _is_clksleep(stm):
    """Check if stm is a clksleep call (excludes wait_until and wait_*)."""
    return (isinstance(stm, EXPR) and isinstance(stm.exp, SYSCALL) and
            stm.exp.name == 'polyphony.timing.clksleep')


class AliasVarDetector(IRVisitor):
    def process(self, scope):
        self.usedef = UseDefDetector().process(scope)
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
        # First, check if def_blk has a clksleep after def_stm
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
                # Check if use_blk has a clksleep before use_stm
                for stm in blk.stms:
                    if stm is use_stm:
                        break
                    if _is_clksleep(stm):
                        return True
                return False
            # Intermediate block contains a clksleep
            for stm in blk.stms:
                if _is_clksleep(stm):
                    return True
            for succ in blk.succs:
                if succ not in visited:
                    queue.append(succ)
        return False

    def visit_CMOVE(self, ir):
        assert isinstance(ir.dst, IRVariable)
        sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym.is_condition() or self.scope.is_comb():
            logger.debug(f'{sym} is alias')
            sym.add_tag('alias')

    def visit_MOVE(self, ir):
        assert isinstance(ir.dst, IRVariable)
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
                # Walk up the parent chain to find the nearest enclosing module scope
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
        if isinstance(ir.src, IRVariable):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            if self.scope.is_ctor() and self.scope.parent.is_module():
                pass
            elif src_sym.is_param() or src_sym.typ.is_port():
                return
        elif isinstance(ir.src, CALL):
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
        elif isinstance(ir.src, NEW):
            return
        elif isinstance(ir.src, SYSCALL):
            if ir.src.name == '$new':
                return
        elif isinstance(ir.src, MREF):
            if sched == 'timed':
                 pass
            else:
                mem_sym = qualified_symbols(ir.src.mem, self.scope)[-1]
                assert isinstance(mem_sym, Symbol)
                stms = self.usedef.get_stms_using(mem_sym)
                for stm in stms:
                    if isinstance(stm, EXPR) and isinstance(stm.exp, MSTORE) and stm.exp.mem == ir.src.mem:
                        return
        elif isinstance(ir.src, ARRAY):
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
            if isinstance(a, TEMP):
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
            if isinstance(a, TEMP):
                arg_syms.append(qualified_symbols(a, self.scope)[-1])
        if any([sym is asym for asym in arg_syms]):
            return
        sym.add_tag('alias')
