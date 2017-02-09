from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .graph import Graph


class StateReducer:
    def process(self, scope):
        if not scope.stgs:
            return
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
