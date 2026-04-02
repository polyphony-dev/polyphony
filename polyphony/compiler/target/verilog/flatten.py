from ...ahdl.ahdl import AHDL_VAR, AHDL_MEMVAR
from ...ahdl.ahdltransformer import AHDLTransformer


class FlattenSignals(AHDLTransformer):
    """Flatten mode: tags pass through unchanged."""

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        existing = self.hdlmodule.signal(ahdl.hdl_name)
        new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, ahdl.sig.tags, ahdl.sig.sym)
        return AHDL_VAR(new_sig, ahdl.ctx)

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        existing = self.hdlmodule.signal(ahdl.hdl_name)
        new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, ahdl.sig.tags, ahdl.sig.sym)
        return AHDL_MEMVAR(new_sig, ahdl.ctx)


class FlattenSignalsIndividual(AHDLTransformer):
    """Individual mode: strip I/O tags from submodule signal chains."""

    _IO_TAGS = {'input', 'output', 'single_port'}
    _REG_NET_TAGS = {'reg', 'net', 'initializable'}

    def _flatten_tags(self, tags, existing_sig=None):
        result = tags - self._IO_TAGS
        # If the target signal already exists (e.g. a connector),
        # don't override its reg/net designation.
        if existing_sig and existing_sig.tags & self._REG_NET_TAGS:
            result = result - self._REG_NET_TAGS
        return result

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        existing = self.hdlmodule.signal(ahdl.hdl_name)
        new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, self._flatten_tags(ahdl.sig.tags, existing), ahdl.sig.sym)
        return AHDL_VAR(new_sig, ahdl.ctx)

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        existing = self.hdlmodule.signal(ahdl.hdl_name)
        new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, self._flatten_tags(ahdl.sig.tags, existing), ahdl.sig.sym)
        return AHDL_MEMVAR(new_sig, ahdl.ctx)
