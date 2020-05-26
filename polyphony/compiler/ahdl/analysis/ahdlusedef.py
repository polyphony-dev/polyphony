from collections import defaultdict
from ..ahdl import *
from ..ahdlvisitor import AHDLVisitor
from logging import getLogger
logger = getLogger(__name__)


class UseDefTable(object):
    def __init__(self):
        self._def_sig2stm = defaultdict(set)
        self._def_stm2sig = defaultdict(set)

        self._use_sig2stm = defaultdict(set)
        self._use_stm2sig = defaultdict(set)

    def add_sig_def(self, sig, stm, state=None):
        self._def_sig2stm[sig].add(stm)
        self._def_stm2sig[stm].add(sig)

    def remove_sig_def(self, sig, stm, state=None):
        self._def_sig2stm[sig].discard(stm)
        self._def_stm2sig[stm].discard(sig)

    def add_sig_use(self, sig, stm, state=None):
        self._use_sig2stm[sig].add(stm)
        self._use_stm2sig[stm].add(sig)

    def remove_sig_use(self, sig, stm, state=None):
        self._use_sig2stm[sig].discard(stm)
        self._use_stm2sig[stm].discard(sig)

    def remove_stm(self, stm):
        for sig in list(self.get_sigs_used_at(stm)):
            self.remove_sig_use(sig, stm)
        for sig in list(self.get_sigs_defined_at(stm)):
            self.remove_sig_def(sig, stm)

    def get_stms_defining(self, sig):
        return self._def_sig2stm[sig]

    def get_sigs_defined_at(self, stm):
        return self._def_stm2sig[stm]

    def get_stms_using(self, sig):
        return self._use_sig2stm[sig]

    def get_sigs_used_at(self, stm):
        return self._use_stm2sig[stm]

    def get_all_def_sigs(self):
        return self._def_sig2stm.keys()

    def __str__(self):
        s = ''
        keys = set(self._def_sig2stm.keys()) | set(self._use_sig2stm.keys())
        for key in sorted(keys):
            s += str(key) + '\n'
            s += '  defs\n'
            if key in self._def_sig2stm:
                stms = self._def_sig2stm[key]
                for stm in stms:
                    s += '    ' + str(stm) + '\n'
            s += '  uses\n'
            if key in self._use_sig2stm:
                stms = self._use_sig2stm[key]
                for stm in stms:
                    s += '    ' + str(stm) + '\n'
        return s


class AHDLUseDefDetector(AHDLVisitor):
    def __init__(self):
        super().__init__()
        self.table = UseDefTable()
        self.enable_use = True
        self.enable_def = True

    def process(self, hdlmodule):
        super().process(hdlmodule)
        hdlmodule.usedef = self.table

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.ctx & Ctx.STORE:
            if self.enable_def:
                self.table.add_sig_def(ahdl.sig, self.current_stm, self.current_state)
        else:
            if self.enable_use:
                self.table.add_sig_use(ahdl.sig, self.current_stm, self.current_state)

    def visit_AHDL_SEQ(self, ahdl):
        method = 'visit_{}'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        visitor(ahdl.factor)
        self.enable_use = True
        self.enable_def = True
