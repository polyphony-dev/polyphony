from ..ahdl import AHDL_VAR, AHDL_MEMVAR
from ..ahdltransformer import AHDLTransformer

class AHDLSignalReplacer(AHDLTransformer):
    def __init__(self, replace_table:dict[tuple, tuple]):
        self._replace_table = replace_table

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.vars in self._replace_table:
            vars = self._replace_table[ahdl.vars]
            return AHDL_VAR(vars, ahdl.ctx)
        else:
            return ahdl

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.vars in self._replace_table:
            vars = self._replace_table[ahdl.vars]
            return AHDL_MEMVAR(vars, ahdl.ctx)
        else:
            return ahdl



