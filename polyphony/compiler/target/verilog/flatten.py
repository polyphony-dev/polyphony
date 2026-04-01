from ...ahdl.ahdl import AHDL_VAR, AHDL_MEMVAR
from ...ahdl.ahdltransformer import AHDLTransformer
from ...common.env import env


class FlattenSignals(AHDLTransformer):
    # Tags that belong to the I/O port declaration context, not to
    # the signal itself.  When individual compilation is active,
    # qualified signal chains may reference submodule I/O ports whose
    # tags should not propagate to the flattened connector signal in
    # the parent scope.
    _IO_TAGS = {'input', 'output', 'single_port'}
    _REG_NET_TAGS = {'reg', 'net', 'initializable'}

    def _flatten_tags(self, tags, existing_sig=None):
        if not env.config.flatten_modules:
            result = tags - self._IO_TAGS
            # If the target signal already exists (e.g. a connector),
            # don't override its reg/net designation.
            if existing_sig and existing_sig.tags & self._REG_NET_TAGS:
                result = result - self._REG_NET_TAGS
            return result
        return tags

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
