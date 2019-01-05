from .ahdlvisitor import AHDLVisitor


class AHDLVarReplacer(AHDLVisitor):
    def replace(self, ahdl, old, new):
        self.old = old
        self.new = new
        self.visit(ahdl)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig == self.old:
            ahdl.sig = self.new
