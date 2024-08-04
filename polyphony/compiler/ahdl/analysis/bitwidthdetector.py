from ..ahdl import *
from ..ahdlvisitor import AHDLVisitor
from ...common.env import env

class BitWidthDetector(AHDLVisitor):
    def visit_AHDL_CONST(self, ahdl):
        if isinstance(ahdl.value, int):
            return env.config.default_int_width
        elif isinstance(ahdl.value, str):
            return 0
        else:
            assert False

    def visit_AHDL_OP(self, ahdl):
        if ahdl.is_relop():
            return 1
        widths = [self.visit(a) for a in ahdl.args]
        return max(widths)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig.is_int():
            return ahdl.sig.width  - 1
        else:
            return ahdl.sig.width

    def visit_AHDL_MEMVAR(self, ahdl):
        assert isinstance(ahdl.sig.width, tuple)
        if ahdl.sig.is_int():
            return ahdl.sig.width[0]  - 1
        else:
            return ahdl.sig.width[0]

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        return self.visit(ahdl.memvar)

    def visit_AHDL_CONCAT(self, ahdl):
        raise NotImplementedError()

    def visit_AHDL_SLICE(self, ahdl):
        raise NotImplementedError()

    def visit_AHDL_FUNCALL(self, ahdl):
        return self.visit(ahdl.name)

    def visit_AHDL_IF_EXP(self, ahdl):
        lw = self.visit(ahdl.lexp)
        rw = self.visit(ahdl.rexp)
        return max((lw, rw))

    def visit(self, ahdl) -> int:
        assert isinstance(ahdl, AHDL_EXP)
        visitor = self.find_visitor(ahdl.__class__)
        assert visitor
        ret = visitor(ahdl)
        if ret is None:
            return 0
        else:
            return ret
