from ..ahdl import *
from ..ahdlvisitor import AHDLVisitor
from ..ahdlhelper import AHDLVarReplacer, AHDLRemover
from logging import getLogger
logger = getLogger(__name__)

class AHDLCopyOpt(AHDLVisitor):
    def process(self, hdlmodule):
        removes = self._remove_alias(hdlmodule)
        AHDLRemover(removes).process(hdlmodule)

    def _remove_alias(self, hdlmodule):
        replacer = AHDLVarReplacer(hdlmodule)
        removes = []
        for sig in hdlmodule.get_signals({'net'}, {'input', 'output', 'condition', 'pipeline_ctrl'}):
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
            if (target.varsig.sym and
                    target.varsig.sym.typ.is_object() and
                    target.varsig.sym.typ.scope.name.startswith('polyphony.Net')):
                continue
            uses = hdlmodule.usedef.get_stms_using(target.varsig)
            if len(uses) == 1 and src.is_a(AHDL_VAR):
                use = list(uses)[0]
                if use.is_a(AHDL_IO_WRITE):
                    # don't change the I/O timing
                    continue
                logger.debug(f'{use} {target.sig} -> {src.sig}')
                replacer.replace(use, target.varsig, src.varsig)
                removes.append(d)
                hdlmodule.remove_sig(target.varsig)
                hdlmodule.remove_signal_decl(target.varsig)

                hdlmodule.usedef.remove_stm(d)
                hdlmodule.usedef.remove_sig_use(target.varsig, use)
                hdlmodule.usedef.add_sig_use(src.varsig, use)
        return removes
