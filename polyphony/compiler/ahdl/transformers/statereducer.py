from collections import deque
from ..ahdl import *
from ..ahdlvisitor import AHDLVisitor, AHDLCollector
from ..ahdltransformer import AHDLTransformer
from ..hdlmodule import FSM
from ...common.graph import Graph
from ..stg_pipeline import PipelineState
from logging import getLogger
logger = getLogger(__name__)


def is_empty_state(state):
    return (not isinstance(state, PipelineState) and
        len(state.block.codes) == 1 and
        state.block.codes[0].is_a(AHDL_TRANSITION) and
        state.block.codes[-1].target_name != state.name)


class StateReducer(object):
    def process(self, hdlmodule):
        IfForwarder().process(hdlmodule)
        EmptyStateSkipper().process(hdlmodule)
        self._remove_unreached_state(hdlmodule)
        self._remove_empty_init_state(hdlmodule)

    def _remove_unreached_state(self, hdlmodule):
        graph = StateGraphBuilder().process(hdlmodule)
        for fsm in hdlmodule.fsms.values():
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
                    elif len(graph.preds(state.name)) == 1 and list(graph.preds(state.name))[0] == state.name:
                        logger.debug(f'Remove state {state.name}')
                        stg.remove_state(state)

    def _remove_empty_init_state(self, hdlmodule):
        empty_stgs = []
        for fsm in hdlmodule.fsms.values():
            for stg in fsm.stgs:
                if is_empty_state(stg.states[0]):
                    stg.remove_state(stg.states[0])
                if not stg.states:
                    empty_stgs.append(stg)
            for stg in empty_stgs:
                fsm.remove_stg(stg)

class StateGraph(Graph):
    def __str__(self):
        s = 'Nodes\n'
        for node in self.get_nodes():
            s += '{}\n'.format(node)
        s += 'Edges\n'
        for edge in self.ordered_edges():
            s += '{} --> {}: {}\n'.format(edge.src, edge.dst, edge.flags)
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

    def visit_AHDL_TRANSITION(self, ahdl):
        next_state = self._get_state(ahdl.target_name)
        if not is_empty_state(next_state):
            return ahdl
        while is_empty_state(next_state) and next_state != self.current_state:
            assert next_state.block.codes[0].is_a(AHDL_TRANSITION)
            next_transition = next_state.block.codes[-1]
            if next_transition.target_name == next_state.name:
                break
            logger.debug(f'{self.current_state.name}: Skip {ahdl.target_name} -> {next_transition.target_name}')
            next_state = self._get_state(next_transition.target_name)
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
                blocks.append(block)
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
        return self.visit(new_ahdl)

    def visit_PipelineState(self, ahdl):
        return ahdl
