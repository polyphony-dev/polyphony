from collections import deque
from .ahdl import *
from .ahdlvisitor import AHDLVisitor, AHDLCollector
from .graph import Graph
from .stg import State
from .stg_pipeline import PipelineState
from .utils import find_only_one_in


class StateReducer(object):
    def process(self, hdlmodule):
        for fsm in hdlmodule.fsms.values():
            WaitForwarder().process(fsm)
            IfForwarder().process(fsm)
            graph = StateGraphBuilder().process(fsm)
            self._remove_unreached_state(fsm, graph)
            self._remove_empty_state(fsm, graph)

    def _remove_unreached_state(self, fsm, graph):
        for stg in fsm.stgs:
            if len(stg.states) == 1:
                continue
            for state in stg.states[:]:
                if not graph.has_node(state):
                    stg.states.remove(state)

    def _remove_empty_state(self, fsm, graph):
        transition_collector = AHDLCollector(AHDL_TRANSITION)
        for stg in fsm.stgs:
            for state in stg.states[:]:
                if (not isinstance(state, PipelineState) and
                        len(state.codes) == 1 and
                        len(graph.preds(state)) == 1 and
                        state.codes[0].is_a(AHDL_TRANSITION)):
                    pred = list(graph.preds(state))[0]
                    transition_collector.process_state(pred)
                    for _, codes in transition_collector.results.items():
                        for c in codes:
                            if c.target is state:
                                c.target = state.codes[0].target
                    stg.states.remove(state)


class StateGraph(Graph):
    pass


class StateGraphBuilder(AHDLVisitor):
    def process(self, fsm):
        self.graph = StateGraph()
        init_state = fsm.stgs[0].init_state
        nexts = deque([init_state])
        visited = set()
        while nexts:
            state = nexts.popleft()
            visited.add(state)
            self.next_states = []
            self.visit(state)
            for next in self.next_states:
                self.graph.add_edge(state, next)
                if next not in visited:
                    nexts.append(next)
        return self.graph

    def visit_AHDL_TRANSITION(self, ahdl):
        assert isinstance(ahdl.target, State)
        self.next_states.append(ahdl.target)


class WaitForwarder(AHDLVisitor):
    def process(self, fsm):
        for stg in fsm.stgs:
            for state in stg.states:
                if isinstance(state, PipelineState):
                    continue
                wait = find_only_one_in(AHDL_META_WAIT, state.codes)
                if wait and wait.transition.target is not state:
                    self.merge_wait_function(wait)
                else:
                    self.visit(state)

    def merge_wait_function(self, wait_func):
        next_state_codes = wait_func.transition.target.codes
        if next_state_codes[-1].is_a(AHDL_META_WAIT):
            return
        if wait_func.codes:
            wait_func.codes.extend(wait_func.transition.target.codes)
        else:
            wait_func.codes = wait_func.transition.target.codes
        # we don't remove the target codes
        # because the target might be reached from an another state
        #wait_func.transition.target.codes = []
        wait_func.transition = None

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        for ahdlblk in ahdl.blocks:
            wait = find_only_one_in(AHDL_META_WAIT, ahdlblk.codes)
            if wait:
                self.merge_wait_function(wait)


class IfForwarder(AHDLVisitor):
    def process(self, fsm):
        self.forwarded = set()
        for stg in fsm.stgs:
            for state in stg.states:
                if isinstance(state, PipelineState):
                    continue
                self.visit(state)

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        if ahdl in self.forwarded:
            return
        for i, ahdlblk in enumerate(ahdl.blocks):
            transition = ahdlblk.codes[-1]
            assert transition.is_a(AHDL_TRANSITION)
            if isinstance(transition.target, PipelineState):
                continue
            ahdlblk.codes.pop()
            ahdl.blocks[i].codes.extend(transition.target.codes[:])
        self.forwarded.add(ahdl)
