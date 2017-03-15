from .ahdl import AHDL_STM


class AHDLVisitor(object):
    def __init__(self):
        pass

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
        for codes in ahdl.codes_list:
            for code in codes:
                self.visit(code)

    def visit_AHDL_IF_EXP(self, ahdl):
        self.visit(ahdl.cond)
        self.visit(ahdl.lexp)
        self.visit(ahdl.rexp)

    def visit_AHDL_MODULECALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_CALLEE_PROLOG(self, ahdl):
        pass

    def visit_AHDL_CALLEE_EPILOG(self, ahdl):
        pass

    def visit_AHDL_FUNCALL(self, ahdl):
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

    def visit_WAIT_EDGE(self, ahdl):
        for var in ahdl.args[2:]:
            self.visit(var)
        if ahdl.codes:
            for code in ahdl.codes:
                self.visit(code)
        if ahdl.transition:
            self.visit(ahdl.transition)

    def visit_WAIT_VALUE(self, ahdl):
        for var in ahdl.args[1:]:
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

    def visit_AHDL_TRANSITION(self, ahdl):
        pass

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit(self, ahdl):
        method = 'visit_' + ahdl.__class__.__name__
        visitor = getattr(self, method, None)
        if ahdl.is_a(AHDL_STM):
            self.current_stm = ahdl
        return visitor(ahdl)
