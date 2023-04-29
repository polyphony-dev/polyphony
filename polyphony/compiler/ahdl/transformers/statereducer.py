from collections import deque
from ..ahdl import *
from ..ahdlvisitor import AHDLVisitor, AHDLCollector
from ..ahdltransformer import AHDLTransformer
from ...common.graph import Graph
from ..stg import State
from ..stg_pipeline import PipelineState


class StateReducer(object):
    def process(self, hdlmodule):
        for fsm in hdlmodule.fsms.values():
            IfForwarder().process(fsm)
            graph = StateGraphBuilder().process_fsm(fsm)
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
                state_codes = state.block.codes
                if (not isinstance(state, PipelineState) and
                        len(state_codes) == 1 and
                        state_codes[0].is_a(AHDL_TRANSITION)):
                    next_state = state.stg.get_state(state_codes[0].target_name)
                    if next_state is state:
                        continue
                    for pred in graph.preds(state):
                        transition_collector.visit(pred)
                        for _, codes in transition_collector.results.items():
                            for c in codes:
                                if c.target_name == state.name:
                                    c.update_target(next_state.name)
                    stg.remove_state(state)
                    graph.del_node_with_reconnect(state)
            if not stg.states:
                remove_stgs.append(stg)
        for stg in fsm.stgs[:]:
            if stg in remove_stgs:
                fsm.stgs.remove(stg)
            if stg.parent in remove_stgs:
                stg.parent = None


class StateGraph(Graph):
    def __str__(self):
        s = 'Nodes\n'
        for node in self.get_nodes():
            s += '{}\n'.format(node.name)
        s += 'Edges\n'
        for edge in self.ordered_edges():
            s += '{} --> {}: {}\n'.format(edge.src.name, edge.dst.name, edge.flags)
        return s



class StateGraphBuilder(AHDLVisitor):
    def process_fsm(self, fsm):
        self.graph = StateGraph()
        super().process_fsm(fsm)
        return self.graph

    def visit_AHDL_TRANSITION(self, ahdl):
        next_state = self.current_stg.get_state(ahdl.target_name)
        self.graph.add_edge(self.current_state, next_state)


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
