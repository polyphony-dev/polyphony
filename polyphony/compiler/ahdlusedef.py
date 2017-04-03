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

    def __str__(self):
        s = '### ahdl statements that has signal defs\n'
        for sig, stms in self._def_sig2stm.items():
            s += str(sig) + '\n'
            for stm in stms:
                s += '    ' + str(stm) + '\n'

        s += '### ahdl statements that has signal uses\n'
        for sig, stms in self._use_sig2stm.items():
            s += str(sig) + '\n'
            for stm in stms:
                s += '    ' + str(stm) + '\n'
        return s


class AHDLUseDefDetector(AHDLVisitor):
    def __init__(self):
        super().__init__()
        self.table = UseDefTable()

    def process(self, scope):
        if not scope.module_info:
            return
        for fsm in scope.module_info.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    self.current_state = state
                    for code in state.codes:
                        self.visit(code)
        scope.ahdlusedef = self.table

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.ctx & Ctx.STORE:
            self.table.add_var_def(ahdl, self.current_stm, self.current_state)
        else:
            self.table.add_var_use(ahdl, self.current_stm, self.current_state)
