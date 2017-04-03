from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .graph import Graph
from .utils import find_only_one_in


class StateReducer(object):
    def process(self, scope):
        if not scope.stgs:
            return
        WaitForwarder().process(scope)
        IfForwarder().process(scope)
        graph = StateGraphBuilder().process(scope)
        self._remove_unreached_state(scope, graph)

    def _remove_unreached_state(self, scope, graph):
        for stg in scope.stgs:
            if len(stg.states) == 1:
                continue
            for state in stg.states[:]:
                if not graph.has_node(state):
                    stg.states.remove(state)


class StateGraph(Graph):
    pass


class StateGraphBuilder(AHDLVisitor):
    def _walk_state(self, init_state, state, visited):
        if state in visited:
            return
        visited.add(state)
        self.next_states = []
        for code in state.codes:
            self.visit(code)
        for next in self.next_states:
            if next is init_state:
                pass
            else:
                self.graph.add_edge(state, next)
                self._walk_state(init_state, next, visited)

    def process(self, scope):
        self.graph = StateGraph()
        visited = set()
        init_state = scope.stgs[0].init_state
        self._walk_state(init_state, init_state, visited)
        return self.graph

    def visit_AHDL_TRANSITION(self, ahdl):
        self.next_states.append(ahdl.target)


class WaitForwarder(AHDLVisitor):
    def process(self, scope):
        for stg in scope.stgs:
            for state in stg.states:
                wait = find_only_one_in(AHDL_META_WAIT, state.codes)
                if wait and wait.transition.target is not state:
                    self.merge_wait_function(wait)
                else:
                    for code in state.codes:
                        self.visit(code)

    def merge_wait_function(self, wait_func):
        next_state_codes = wait_func.transition.target.codes
        if next_state_codes[-1].is_a(AHDL_META_WAIT):
            return
        if wait_func.codes:
            wait_func.codes.extend(wait_func.transition.target.codes)
        else:
            wait_func.codes = wait_func.transition.target.codes
        wait_func.transition.target.codes = []
        wait_func.transition = None

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        for codes in ahdl.codes_list:
            wait = find_only_one_in(AHDL_META_WAIT, codes)
            if wait:
                self.merge_wait_function(wait)


class IfForwarder(AHDLVisitor):
    def process(self, scope):
        for stg in scope.stgs:
            for state in stg.states:
                for code in state.codes:
                    self.visit(code)

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        for i, codes in enumerate(ahdl.codes_list):
            assert len(codes) == 1
            transition = codes[0]
            assert transition.is_a(AHDL_TRANSITION)
            ahdl.codes_list[i] = transition.target.codes[:]
