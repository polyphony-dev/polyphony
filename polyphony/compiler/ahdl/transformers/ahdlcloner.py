from ..ahdltransformer import AHDLTransformer
from ..ahdl import *

class AHDLCloner(AHDLTransformer):
    def __init__(self, sig_maps: dict[str, dict[Signal, Signal]]):
        super().__init__()
        self.sig_maps = sig_maps

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.vars[0].hdlscope.scope.is_namespace():
            return ahdl
        signals = tuple([self.sig_maps[sig.hdlscope.name][sig] for sig in ahdl.vars])
        return AHDL_VAR(signals, ahdl.ctx)

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.vars[0].hdlscope.scope.is_namespace():
            return ahdl
        signals = tuple([self.sig_maps[sig.hdlscope.name][sig] for sig in ahdl.vars])
        return AHDL_MEMVAR(signals, ahdl.ctx)

    def visit_AHDL_EVENT_TASK(self, ahdl):
        events = tuple([(self.sig_maps[sig.hdlscope.name][sig], edge) for sig, edge in ahdl.events])
        return AHDL_EVENT_TASK(events, self.visit(ahdl.stm))
