from .ahdl import *
from .ahdlvisitor import AHDLVisitor


class StateReducer(AHDLVisitor):
    def __init__(self):
        pass

    def process(self, scope):
        for stg in scope.stgs:
            if stg.is_main():
                self.main_stg = stg
                break
        self.using_state = set()
        for stg in scope.stgs:
            self.current_stg = stg
            
            for state in stg.states:
                self.current_state = state
                for code in state.codes:
                    self.visit(code)
        for stg in scope.stgs:
            for state in stg.states[:]:
                if state not in self.using_state:# and state is not self.main_stg.finish_state and state is not self.main_stg.init_state:
                    stg.states.remove(state)

    def _next_state(self):
        next_idx = self.current_stg.states.index(self.current_state) + 1
        if next_idx < len(self.current_stg.states):
            return self.current_stg.states[next_idx]
        else:
            return None

    def visit_AHDL_IF(self, ahdl):
        for idx, codes in enumerate(ahdl.codes_list):
            if len(codes) == 1 and codes[0].is_a(AHDL_TRANSITION):
                next_state = codes[0].target
                if next_state is self.main_stg.finish_state:
                    continue
                ahdl.codes_list[idx] = next_state.codes[:]
                #next_state.codes = []
        for codes in ahdl.codes_list:
            for c in codes:
                self.visit(c)

    def visit_AHDL_TRANSITION(self, ahdl):
        self.using_state.add(ahdl.target)

