from collections import defaultdict
from .ahdl import AHDL_STM


class AHDLVisitor(object):
    def __init__(self):
        self.current_fsm = None
        self.current_stg = None
        self.current_state = None

    def process(self, hdlmodule):
        for fsm in hdlmodule.fsms.values():
            self.process_fsm(fsm)

    def process_fsm(self, fsm):
        self.current_fsm = fsm
        for stg in fsm.stgs:
            self.process_stg(stg)

    def process_stg(self, stg):
        self.current_stg = stg
        for state in stg.states:
            self.process_state(state)

    def process_state(self, state):
        self.current_state = state
        self.visit(state)

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_VAR(self, ahdl):
        pass

    def visit_AHDL_MEMVAR(self, ahdl):
        pass

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        self.visit(ahdl.memvar)
        self.visit(ahdl.offset)

    def visit_AHDL_OP(self, ahdl):
        for a in ahdl.args:
            self.visit(a)

    def visit_AHDL_SYMBOL(self, ahdl):
        pass

    def visit_AHDL_CONCAT(self, ahdl):
        for var in ahdl.varlist:
            self.visit(var)

    def visit_AHDL_SLICE(self, ahdl):
        self.visit(ahdl.var)
        self.visit(ahdl.hi)
        self.visit(ahdl.lo)

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_INLINE(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.dst)

    def visit_AHDL_STORE(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.mem)
        self.visit(ahdl.offset)

    def visit_AHDL_LOAD(self, ahdl):
        self.visit(ahdl.mem)
        self.visit(ahdl.dst)
        self.visit(ahdl.offset)

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

    def visit_AHDL_IF_EXP(self, ahdl):
        self.visit(ahdl.cond)
        self.visit(ahdl.lexp)
        self.visit(ahdl.rexp)

    def visit_AHDL_CASE(self, ahdl):
        self.visit(ahdl.sel)
        for item in ahdl.items:
            self.visit(item)

    def visit_AHDL_CASE_ITEM(self, ahdl):
        #self.visit(ahdl.val)
        self.visit(ahdl.block)

    def visit_AHDL_MODULECALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_CALLEE_PROLOG(self, ahdl):
        pass

    def visit_AHDL_CALLEE_EPILOG(self, ahdl):
        pass

    def visit_AHDL_FUNCALL(self, ahdl):
        self.visit(ahdl.name)
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_PROCCALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_META(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ahdl)

    def visit_MEM_MUX(self, ahdl):
        prefix = ahdl.args[0]
        dst = ahdl.args[1]
        srcs = ahdl.args[2]
        conds = ahdl.args[3]
        self.visit(dst)
        for s in srcs:
            self.visit(s)
        for c in conds:
            self.visit(c)

    def visit_WAIT_EDGE(self, ahdl):
        for var in ahdl.args[2:]:
            self.visit(var)
        if ahdl.codes:
            for code in ahdl.codes:
                self.visit(code)
        if ahdl.transition:
            self.visit(ahdl.transition)

    def visit_WAIT_VALUE(self, ahdl):
        for value, var in ahdl.args:
            self.visit(value)
            self.visit(var)
        if ahdl.codes:
            for code in ahdl.codes:
                self.visit(code)
        if ahdl.transition:
            self.visit(ahdl.transition)

    def visit_AHDL_META_WAIT(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ahdl)

    def visit_AHDL_META_MULTI_WAIT(self, ahdl):
        for w in ahdl.waits:
            self.visit(w)
        if ahdl.transition:
            self.visit(ahdl.transition)

    def visit_AHDL_TRANSITION(self, ahdl):
        pass

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_BLOCK(self, ahdl):
        for c in ahdl.codes:
            self.visit(c)

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
