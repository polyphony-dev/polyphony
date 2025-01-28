from collections import defaultdict
from typing import Optional
from .ahdl import AHDL, AHDL_STM, State
from .stg import STG
from .hdlmodule import FSM

class AHDLVisitor(object):
    def __init__(self):
        self.current_fsm: FSM = None  # type: ignore
        self.current_stg: STG = None  # type: ignore
        self.current_state: State = None  # type: ignore
        self.current_stm: AHDL_STM = None  # type: ignore

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        for decl in hdlmodule.decls:
            self.visit(decl)
        for var, old, new in hdlmodule.edge_detectors:
            self.visit(var)
            self.visit(old)
            self.visit(new)
        for fsm in hdlmodule.fsms.values():
            self.process_fsm(fsm)

    def process_fsm(self, fsm):
        self.current_fsm = fsm
        for stm in fsm.reset_stms:
            self.visit(stm)
        for stg in fsm.stgs:
            self.process_stg(stg)

    def process_stg(self, stg):
        self.current_stg = stg
        for state in stg.states:
            self.visit(state)

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_OP(self, ahdl):
        for a in ahdl.args:
            self.visit(a)

    def visit_AHDL_META_OP(self, ahdl):
        for a in ahdl.args:
            if isinstance(a, AHDL):
                self.visit(a)

    def visit_AHDL_VAR(self, ahdl):
        pass

    def visit_AHDL_MEMVAR(self, ahdl):
        pass

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        self.visit(ahdl.memvar)
        self.visit(ahdl.offset)

    def visit_AHDL_SYMBOL(self, ahdl):
        pass

    def visit_AHDL_CONCAT(self, ahdl):
        for var in ahdl.varlist:
            self.visit(var)

    def visit_AHDL_SLICE(self, ahdl):
        self.visit(ahdl.var)
        self.visit(ahdl.hi)
        self.visit(ahdl.lo)

    def visit_AHDL_FUNCALL(self, ahdl):
        self.visit(ahdl.name)
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_IF_EXP(self, ahdl):
        self.visit(ahdl.cond)
        self.visit(ahdl.lexp)
        self.visit(ahdl.rexp)

    def visit_AHDL_BLOCK(self, ahdl):
        for c in ahdl.codes:
            self.visit(c)

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_INLINE(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.dst)

    def visit_AHDL_ASSIGN(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.dst)

    def visit_AHDL_FUNCTION(self, ahdl):
        self.visit(ahdl.output)
        for inp in ahdl.inputs:
            self.visit(inp)
        for stm in ahdl.stms:
            self.visit(stm)

    def visit_AHDL_COMB(self, ahdl):
        for stm in ahdl.stms:
            self.visit(stm)

    def visit_AHDL_EVENT_TASK(self, ahdl):
        self.visit(ahdl.stm)

    def visit_AHDL_CONNECT(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.dst)

    def visit_AHDL_IO_READ(self, ahdl):
        self.visit(ahdl.io)
        if ahdl.dst:
            self.visit(ahdl.dst)

    def visit_AHDL_IO_WRITE(self, ahdl):
        self.visit(ahdl.io)
        self.visit(ahdl.src)

    def visit_AHDL_SEQ(self, ahdl):
        method = 'visit_{}'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        return visitor(ahdl.factor)

    def visit_AHDL_IF(self, ahdl):
        for cond in ahdl.conds:
            if cond:
                self.visit(cond)
        for ahdlblk in ahdl.blocks:
            self.visit(ahdlblk)

    def visit_AHDL_MODULECALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_CALLEE_PROLOG(self, ahdl):
        pass

    def visit_AHDL_CALLEE_EPILOG(self, ahdl):
        pass

    def visit_AHDL_PROCCALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_META_WAIT(self, ahdl):
        for arg in ahdl.args:
            if isinstance(arg, AHDL):
                self.visit(arg)

    def visit_AHDL_CASE_ITEM(self, ahdl):
        self.visit(ahdl.val)
        self.visit(ahdl.block)

    def visit_AHDL_CASE(self, ahdl):
        self.visit(ahdl.sel)
        for item in ahdl.items:
            self.visit(item)

    def visit_AHDL_TRANSITION(self, ahdl):
        pass

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_State(self, state):
        self.current_state = state
        self.visit(state.block)

    def visit_PipelineState(self, state):
        self.current_state = state
        self.visit(state.block)
        # raise NotImplementedError()

    def visit_PipelineStage(self, stage):
        self.visit(stage.block)
        #raise NotImplementedError()

    def find_visitor(self, cls):
        method = 'visit_' + cls.__name__
        visitor = getattr(self, method, None)
        if not visitor:
            for base in cls.__bases__:
                visitor = self.find_visitor(base)
                if visitor:
                    break
        return visitor

    def visit(self, ahdl):
        if ahdl.is_a(AHDL_STM):
            self.current_stm = ahdl
        visitor = self.find_visitor(ahdl.__class__)
        return visitor(ahdl)


class AHDLCollector(AHDLVisitor):
    def __init__(self, ahdl_cls):
        super().__init__()
        self.ahdl_cls = ahdl_cls
        self.results = defaultdict(list)

    def visit(self, ahdl):
        if ahdl.__class__ is self.ahdl_cls:
            self.results[self.current_state].append(ahdl)
        super().visit(ahdl)
