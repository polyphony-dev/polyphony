from ...ahdl.ahdl import AHDL_VAR, AHDL_MEMVAR
from ...ahdl.ahdltransformer import AHDLTransformer

class FlattenSignals(AHDLTransformer):
    def visit_AHDL_VAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, ahdl.sig.tags, ahdl.sig.sym)
        return AHDL_VAR(new_sig, ahdl.ctx)

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, ahdl.sig.tags, ahdl.sig.sym)
        return AHDL_MEMVAR(new_sig, ahdl.ctx)
