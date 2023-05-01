from collections import deque
from ..ahdl import *
from ..ahdlvisitor import AHDLVisitor, AHDLCollector
from ..ahdltransformer import AHDLTransformer
from ..hdlmodule import FSM
from ...common.graph import Graph
from ..stg_pipeline import PipelineState
from logging import getLogger
logger = getLogger(__name__)


class StateReducer(object):
    def process(self, hdlmodule):
        IfForwarder().process(hdlmodule)
        EmptyStateSkipper().process(hdlmodule)
        graph = StateGraphBuilder().process(hdlmodule)
        for fsm in hdlmodule.fsms.values():
            self._remove_unreached_state(fsm, graph)

    def _remove_unreached_state(self, fsm:FSM, graph):
        for stg in fsm.stgs:
            if len(stg.states) == 1:
                continue
            for state in stg.states[1:]:  # skip initial state
                if not graph.has_node(state.name):
                    logger.debug(f'Remove state {state.name}')
                    stg.remove_state(state)
                elif not graph.preds(state.name):
                    logger.debug(f'Remove state {state.name}')
                    stg.remove_state(state)


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
    def process(self, hdlmodule):
        self.graph = StateGraph()
        super().process(hdlmodule)
        return self.graph

    def visit_AHDL_TRANSITION(self, ahdl):
        for stg in self.current_fsm.stgs:
            if stg.has_state(ahdl.target_name):
                next_state = stg.get_state(ahdl.target_name)
                self.graph.add_edge(self.current_state.name, next_state.name)
                return


class EmptyStateSkipper(AHDLTransformer):
    def _get_state(self, target_name):
        for stg in self.current_fsm.stgs:
            if stg.has_state(target_name):
                return stg.get_state(target_name)
        assert False

    def _is_empty(self, state):
        return (not isinstance(state, PipelineState) and
            len(state.block.codes) == 1 and
            state.block.codes[0].is_a(AHDL_TRANSITION))

    def visit_AHDL_TRANSITION(self, ahdl):
        next_state = self._get_state(ahdl.target_name)
        if not self._is_empty(next_state):
            return ahdl
        assert next_state.block.codes[0].is_a(AHDL_TRANSITION)
        next_transition = next_state.block.codes[0]
        logger.debug(f'{self.current_state.name}: Skip {ahdl.target_name} -> {next_transition.target_name}')
        return AHDL_TRANSITION(next_transition.target_name)


class IfForwarder(AHDLTransformer):
    def _get_state(self, target_name):
        for stg in self.current_fsm.stgs:
            if stg.has_state(target_name):
                return stg.get_state(target_name)
        assert False

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        blocks = []
        for block in ahdl.blocks:
            transition = block.codes[-1]
            assert transition.is_a(AHDL_TRANSITION)
            target_state = self._get_state(transition.target_name)
            if isinstance(target_state, PipelineState):
                continue
            codes = list(block.codes)
            codes.pop()
            codes.extend(target_state.block.codes[:])
            new_block = AHDL_BLOCK(block.name, tuple(codes))
            blocks.append(new_block)
        new_ahdl = AHDL_IF(ahdl.conds, tuple(blocks))
        logger.debug(f'Forwarded AHDL_TRANSITION_IF:')
        logger.debug(f'{ahdl}')
        logger.debug(f'{new_ahdl}')
        return new_ahdl

    def visit_PipelineState(self, ahdl):
        return ahdl
