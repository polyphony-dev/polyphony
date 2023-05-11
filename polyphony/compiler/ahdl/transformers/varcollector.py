from collections import defaultdict
from ..ahdl import AHDL_VAR
from ..ahdlvisitor import AHDLVisitor
from ..signal import Signal
from ...ir.ir import Ctx

class AHDLVarCollector(AHDLVisitor):
    '''This class collects variables of various characteristics'''
    def process(self, hdlmodule):
        self._defs = defaultdict(set)
        self._uses = defaultdict(set)
        self._outputs = defaultdict(set)
        self._module_constants = [c for c, _ in hdlmodule.constants.keys()]
        self._mems = defaultdict(set)
        super().process(hdlmodule)

    def def_vars(self, fsm_name) -> set[tuple[Signal]]:
        return self._defs[fsm_name]

    def use_vars(self, fsm_name) -> set[tuple[Signal]]:
        return self._uses[fsm_name]

    def submodule_vars(self, fsm_name=None) -> set[tuple[Signal]]:
        return self.submodule_def_vars(fsm_name) | self.submodule_use_vars(fsm_name)

    def submodule_def_vars(self, fsm_name=None) -> set[tuple[Signal]]:
        results = set()
        if fsm_name is None:
            for defs in self._defs.values():
                for vars in defs:
                    if len(vars) > 1:
                        results.add(vars)
        else:
            for vars in self._defs[fsm_name]:
                if len(vars) > 1:
                    results.add(vars)
        return results

    def submodule_use_vars(self, fsm_name=None) -> set[tuple[Signal]]:
        results = set()
        if fsm_name is None:
            for uses in self._uses.values():
                for vars in uses:
                    if len(vars) > 1:
                        results.add(vars)
        else:
            for vars in self._uses[fsm_name]:
                if len(vars) > 1:
                    results.add(vars)
        return results

    def output_vars(self, fsm_name) -> set[tuple[Signal]]:
        return self._outputs[fsm_name]

    def mem_vars(self, fsm_name) -> set[tuple[Signal]]:
        return self._mems[fsm_name]

    def visit_AHDL_MEMVAR(self, ahdl):
        if self.current_fsm:
            tag = self.current_fsm.name
        else:
            tag = ''

        if ahdl.ctx & Ctx.STORE:
            self._defs[tag].add(ahdl.vars)
        else:
            self._uses[tag].add(ahdl.vars)
        self._mems[tag].add(ahdl.vars)

    def visit_AHDL_VAR(self, ahdl):
        if self.current_fsm:
            tag = self.current_fsm.name
        else:
            tag = ''

        if ahdl.ctx & Ctx.STORE:
            self._defs[tag].add(ahdl.vars)
        else:
            self._uses[tag].add(ahdl.vars)

        if ahdl.sig.is_ctrl() or ahdl.sig in self._module_constants:
            pass
        elif ahdl.sig.is_input():
            if ahdl.sig.is_single_port():
                self._outputs[tag].add(ahdl.vars)
        elif ahdl.sig.is_output():
            self._outputs[tag].add(ahdl.vars)
