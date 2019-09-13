from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .ahdlhelper import AHDLVarReplacer, AHDLRemover


class AHDLCopyOpt(AHDLVisitor):
    def process(self, hdlmodule):
        removes = self._remove_alias(hdlmodule)
        AHDLRemover(removes).process(hdlmodule)

    def _remove_alias(self, hdlmodule):
        replacer = AHDLVarReplacer()
        removes = []
        sigs = list(hdlmodule.signals.values())
        for sig in sigs:
            if not sig.is_net():
                continue
            if sig.is_input() or sig.is_output():
                continue
            if sig.is_condition():
                continue
            if sig.is_pipeline_ctrl():
                continue

            defs = hdlmodule.usedef.get_stms_defining(sig)
            if len(defs) > 1:
                continue
            if len(defs) == 0:
                #print('!!!', sig)
                continue
            d = list(defs)[0]
            if d.is_a(AHDL_IO_READ):
                target = d.dst
                src = d.io
            elif d.is_a(AHDL_MOVE):
                target = d.dst
                src = d.src
            elif d.is_a(AHDL_ASSIGN):
                target = d.dst
                src = d.src
            else:
                print(d)
                assert False
            if (target.sig.sym and
                    target.sig.sym.typ.is_object() and
                    target.sig.sym.typ.get_scope().name.startswith('polyphony.Net')):
                continue
            uses = hdlmodule.usedef.get_stms_using(target.sig)
            if len(uses) == 1 and src.is_a(AHDL_VAR):
                use = list(uses)[0]
                #print(use, target.sig, '->', src.sig)
                replacer.replace(use, target.sig, src.sig)
                removes.append(d)
                hdlmodule.remove_sig(target.sig)
                hdlmodule.remove_signal_decl(target.sig)

                hdlmodule.usedef.remove_stm(d)
                hdlmodule.usedef.remove_sig_use(target.sig, use)
                hdlmodule.usedef.add_sig_use(src.sig, use)
        return removes
