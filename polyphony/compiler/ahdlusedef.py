from collections import defaultdict
from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from logging import getLogger
logger = getLogger(__name__)


class UseDefTable(object):
    def __init__(self):
        self._def_sig2stm = defaultdict(set)
        self._def_stm2sig = defaultdict(set)

        self._def_var2stm = defaultdict(set)
        self._def_stm2var = defaultdict(set)

        self._use_sig2stm = defaultdict(set)
        self._use_stm2sig = defaultdict(set)

        self._use_var2stm = defaultdict(set)
        self._use_stm2var = defaultdict(set)

    def add_var_def(self, var, stm, state):
        assert var.is_a(AHDL_VAR) and stm.is_a(AHDL_STM)
        self._def_sig2stm[var.sig].add(stm)
        self._def_stm2sig[stm].add(var.sig)
        self._def_var2stm[var].add(stm)
        self._def_stm2var[stm].add(var)

    def remove_var_def(self, var, stm, state):
        assert var.is_a(AHDL_VAR) and stm.is_a(AHDL_STM)
        self._def_sig2stm[var.sig].discard(stm)
        self._def_stm2sig[stm].discard(var.sig)
        self._def_var2stm[var].discard(stm)
        self._def_stm2var[stm].discard(var)

    def add_var_use(self, var, stm, state):
        assert var.is_a(AHDL_VAR) and stm.is_a(AHDL_STM)
        self._use_sig2stm[var.sig].add(stm)
        self._use_stm2sig[stm].add(var.sig)
        self._use_var2stm[var].add(stm)
        self._use_stm2var[stm].add(var)

    def remove_var_use(self, var, stm, state):
        assert var.is_a(AHDL_VAR) and stm.is_a(AHDL_STM)
        self._use_sig2stm[var.sig].discard(stm)
        self._use_stm2sig[stm].discard(var.sig)
        self._use_var2stm[var].discard(stm)
        self._use_stm2var[stm].discard(var)

    def get_stms_defining(self, key):
        if isinstance(key, Signal):
            return self._def_sig2stm[key]
        elif isinstance(key, AHDL_VAR):
            return self._def_var2stm[key]

    def get_sigs_defined_at(self, stm):
        if isinstance(stm, AHDL_STM):
            return self._def_stm2sig[stm]

    def get_vars_defined_at(self, stm):
        if isinstance(stm, AHDL_STM):
            return self._def_stm2var[stm]

    def get_stms_using(self, key):
        if isinstance(key, Signal):
            return self._use_sig2stm[key]
        elif isinstance(key, AHDL_VAR):
            return self._use_var2stm[key]

    def get_sigs_used_at(self, stm):
        if isinstance(stm, AHDL_STM):
            return self._use_stm2sig[stm]

    def get_vars_used_at(self, stm):
        if isinstance(stm, AHDL_STM):
            return self._use_stm2var[stm]

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
        for fsm in hdlmodule.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    self.current_state = state
                    self.visit(state)
            fsm.usedef = self.table

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.ctx & Ctx.STORE:
            if self.enable_def:
                self.table.add_var_def(ahdl, self.current_stm, self.current_state)
        else:
            if self.enable_use:
                self.table.add_var_use(ahdl, self.current_stm, self.current_state)

    def visit_AHDL_SEQ(self, ahdl):
        if ahdl.factor.is_a([AHDL_LOAD, AHDL_IO_READ]):
            if ahdl.step == 0:
                # only first item can be valid 'use' in load sequence
                self.enable_def = False
            elif ahdl.step == ahdl.step_n - 1:
                # only last item can be valid 'def' in load sequence
                self.enable_use = False
            else:
                self.enable_def = False
                self.enable_use = False
        elif ahdl.factor.is_a([AHDL_STORE, AHDL_IO_WRITE]):
            if ahdl.step == 0:
                # only first item can be valid 'use' in store sequence
                pass
            else:
                self.enable_use = False
        method = 'visit_{}'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        ret = visitor(ahdl.factor)
        self.enable_use = True
        self.enable_def = True
