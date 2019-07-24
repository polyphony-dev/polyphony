from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .ahdlhelper import AHDLVarReplacer, AHDLRemover


class AHDLCopyOpt(AHDLVisitor):
    def __init__(self):
        self.replacer = AHDLVarReplacer()

    def process(self, hdlmodule):
        self.removes = []
        super().process(hdlmodule)
        AHDLRemover(self.removes).process(hdlmodule)

    def process_fsm(self, fsm):
        for sig in list(self.hdlmodule.signals.values()):
            if not sig.is_net():
                continue
            if sig.is_input() or sig.is_output():
                continue
            if sig.is_condition():
                continue

            defs = fsm.usedef.get_stms_defining(sig)
            if len(defs) > 1:
                continue
            if len(defs) == 0:
                #print('!!!', sig)
                continue
            d = list(defs)[0]
            if d.is_a(AHDL_IO_READ):
                target = d.dst.sig
                src = d.io
            elif d.is_a(AHDL_MOVE):
                target = d.dst.sig
                src = d.src
            else:
                print(d)
                assert False
            uses = fsm.usedef.get_stms_using(target)
            if len(uses) == 1 and src.is_a(AHDL_VAR):
                use = list(uses)[0]
                #print(use, target, '->', src.sig)
                self.replacer.replace(use, target, src.sig)
                self.removes.append(d)
                self.hdlmodule.remove_sig(target)
                self.hdlmodule.remove_signal_decl(target)
