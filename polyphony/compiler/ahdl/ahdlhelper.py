from .ahdlvisitor import AHDLVisitor


class AHDLVarReplacer(AHDLVisitor):
    def replace(self, ahdl, old, new):
        self.old = old
        self.new = new
        self.visit(ahdl)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig == self.old:
            ahdl.sig = self.new


class AHDLRemover(AHDLVisitor):
    def __init__(self, removes):
        self.removes = removes

    def visit_AHDL_BLOCK(self, ahdl):
        for rm in self.removes:
            if rm in ahdl.codes:
                ahdl.codes.remove(rm)
