from ..ahdl import *
from ..ahdltransformer import AHDLTransformer
from ..analysis.ahdlusedef import AHDLUseDefDetector
from logging import getLogger
logger = getLogger(__name__)


class AHDLCopyOpt(AHDLTransformer):
    def process(self, hdlmodule):
        self.updated = True
        while self.updated:
            self.updated = False
            self.usedef = AHDLUseDefDetector().process(hdlmodule)
            super().process(hdlmodule)
            logger.debug(str(hdlmodule))

            AHDLVarReducer().process(hdlmodule)
            #logger.debug('!!! after reduce')
            #logger.debug(str(hdlmodule))

    def _is_ignore_case(self, target:AHDL_VAR) -> bool:
        return (target.varsig.sym and
            target.varsig.sym.typ.is_object() and
            target.varsig.sym.typ.scope.name.startswith('polyphony.Net'))

    def _get_new_src(self, src_def:AHDL_STM) -> AHDL_EXP:
        if src_def.is_a(AHDL_MOVE):
            new_src = cast(AHDL_MOVE, src_def).src
        elif src_def.is_a(AHDL_ASSIGN):
            new_src = cast(AHDL_ASSIGN, src_def).src
        elif src_def.is_a(AHDL_IO_READ):
            new_src = cast(AHDL_IO_READ, src_def).io
        else:
            assert False
        return new_src

    def visit_AHDL_VAR(self, ahdl:AHDL_VAR) -> AHDL_EXP:
        if ahdl.ctx != Ctx.LOAD or ahdl.sig.is_net():
            return super().visit_AHDL_VAR(ahdl)

        src_defs = self.usedef.get_def_stms(ahdl.sig)
        if len(src_defs) != 1 or self._is_ignore_case(ahdl):
            return super().visit_AHDL_VAR(ahdl)

        new_src = self._get_new_src(list(src_defs)[0])
        logger.debug(f'replace {ahdl} -> {new_src}')
        self.updated = True
        return new_src

    def visit_AHDL_STRUCT(self, ahdl):
        # ignore attribute of object
        return ahdl


class AHDLVarReducer(AHDLTransformer):
    def process(self, hdlmodule):
        self.usedef = AHDLUseDefDetector().process(hdlmodule)
        super().process(hdlmodule)

    def _can_reduce(self, lvalue):
        if lvalue.is_a(AHDL_VAR):
            dst_uses = self.usedef.get_use_stms(cast(AHDL_VAR, lvalue).varsig)
            var = cast(AHDL_VAR, lvalue)
        else:
            return False
        if len(dst_uses):
            return False
        if var.varsig.is_output():
            return False
        if var.varsig.is_extport():
            return False
        return True

    def visit_AHDL_MOVE(self, ahdl):
        if self._can_reduce(ahdl.dst):
            logger.debug(f'reduce {ahdl}')
            if self.hdlmodule.signal(ahdl.dst.varsig.name):
                self.hdlmodule.remove_sig(ahdl.dst.varsig)
            return AHDL_NOP('')
        return super().visit_AHDL_MOVE(ahdl)

    def visit_AHDL_ASSIGN(self, ahdl):
        if self._can_reduce(ahdl.dst):
            logger.debug(f'reduce {ahdl}')
            if self.hdlmodule.signal(ahdl.dst.varsig.name):
                self.hdlmodule.remove_sig(ahdl.dst.varsig)
            return AHDL_NOP('')
        return super().visit_AHDL_ASSIGN(ahdl)

    def visit_AHDL_IO_READ(self, ahdl):
        if self._can_reduce(ahdl.dst):
            logger.debug(f'reduce {ahdl}')
            if self.hdlmodule.signal(ahdl.dst.varsig.name):
                self.hdlmodule.remove_sig(ahdl.dst.varsig)
            return AHDL_NOP('')
        return super().visit_AHDL_IO_READ(ahdl)
