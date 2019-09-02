from collections import deque
from .ahdl import *
from .ahdlvisitor import AHDLVisitor, AHDLCollector
from .graph import Graph
from .stg import State
from .stg_pipeline import PipelineState


class StateReducer(object):
    def process(self, hdlmodule):
        for fsm in hdlmodule.fsms.values():
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
        remove_stgs = []
        for stg in fsm.stgs:
            for state in stg.states[:]:
                if (not isinstance(state, PipelineState) and
                        len(state.codes) == 1 and
                        state.codes[0].is_a(AHDL_TRANSITION)):
                    next_state = state.codes[0].target
                    if next_state is state:
                        continue
                    for pred_i in range(len(graph.preds(state))):
                        pred = list(graph.preds(state))[pred_i]
                        transition_collector.process_state(pred)
                        for _, codes in transition_collector.results.items():
                            for c in codes:
                                if c.target is state:
                                    if state is stg.finish_state is next_state:
                                        c.target = pred
                                    else:
                                        c.target = next_state
                    if stg.init_state is state:
                        stg.init_state = next_state
                    stg.states.remove(state)
                    graph.del_node_with_reconnect(state)
            if not stg.states:
                remove_stgs.append(stg)
        for stg in fsm.stgs[:]:
            if stg in remove_stgs:
                fsm.stgs.remove(stg)
            if stg.parent in remove_stgs:
                stg.parent = None


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
