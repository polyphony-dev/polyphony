from .ahdl import AHDL_VAR, AHDL_BLOCK
from .ahdltransformer import AHDLTransformer


class AHDLVarReplacer(AHDLTransformer):
    def __init__(self, hdlmodule):
        self.hdlmodule = hdlmodule
        super().__init__()

    def replace(self, ahdl, old, new):
        self.old = old
        self.new = new
        self.visit(ahdl)

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig == self.old:
            return AHDL_VAR(self.new, ahdl.ctx)
        return super().visit_AHDL_VAR(ahdl)


class AHDLRemover(AHDLTransformer):
    def __init__(self, removes):
        self.removes = removes

    def visit_AHDL_BLOCK(self, ahdl):
        codes = list(ahdl.codes)
        for rm in self.removes:
            if rm in codes:
                codes.remove(rm)
        return AHDL_BLOCK(ahdl.name, tuple(codes))
