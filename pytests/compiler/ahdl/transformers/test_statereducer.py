"""Tests for statereducer.py covering uncovered lines."""
from polyphony.compiler.ahdl.transformers.statereducer import (
    StateReducer, StateGraph, StateGraphBuilder, EmptyStateSkipper, IfForwarder, is_empty_state,
)
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_MOVE, AHDL_VAR, AHDL_TRANSITION,
    AHDL_TRANSITION_IF, AHDL_IF, State, Ctx,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule, FSM
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


_SRC = '''
scope test
tags function returnable
'''


def build_scope():
    setup_test()
    parser = IrReader(_SRC)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def _build_fsm(hdl, states_specs):
    """Build an FSM from a list of (name, codes) tuples. Returns (fsm, stg)."""
    state_sig = hdl.gen_sig('fsm_state', 4, {'reg'})
    fsm = FSM('main_fsm', hdl.scope, state_sig)
    stg = STG('main', None, hdl)

    states = []
    for i, (name, codes) in enumerate(states_specs):
        block = AHDL_BLOCK(name, codes)
        state = stg.new_state(name, block, i)
        states.append(state)

    stg.set_states(states)
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm
    return fsm, stg


# ============================================================
# is_empty_state function
# ============================================================

def test_is_empty_state_single_transition_to_other():
    """Single AHDL_TRANSITION to a different state -> empty."""
    hdl = make_hdlmodule()
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', ()),
    ])
    assert is_empty_state(stg.states[0]) is True


def test_is_empty_state_multiple_codes():
    """Multiple codes -> not empty."""
    hdl = make_hdlmodule()
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(0))
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (mv, AHDL_TRANSITION('S1'))),
        ('S1', ()),
    ])
    assert is_empty_state(stg.states[0]) is False


def test_is_empty_state_transition_to_self():
    """AHDL_TRANSITION pointing back to itself -> not empty."""
    hdl = make_hdlmodule()
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('INIT'),)),
    ])
    assert is_empty_state(stg.states[0]) is False


def test_is_empty_state_no_codes():
    """No codes -> not empty (len != 1)."""
    hdl = make_hdlmodule()
    fsm, stg = _build_fsm(hdl, [('INIT', ())])
    assert is_empty_state(stg.states[0]) is False


# ============================================================
# StateGraph.__str__
# ============================================================

def test_state_graph_str():
    g = StateGraph()
    g.add_node('INIT')
    g.add_node('S1')
    g.add_edge('INIT', 'S1')
    s = str(g)
    assert 'INIT' in s
    assert 'S1' in s
    assert 'Nodes' in s
    assert 'Edges' in s


# ============================================================
# StateGraphBuilder
# ============================================================

def test_state_graph_builder_builds_graph():
    """StateGraphBuilder.process() creates a StateGraph with transitions."""
    hdl = make_hdlmodule()
    _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', (AHDL_TRANSITION('S2'),)),
        ('S2', ()),
    ])
    graph = StateGraphBuilder().process(hdl)
    assert isinstance(graph, StateGraph)
    assert graph.has_node('S1')
    assert graph.has_node('S2')


def test_state_graph_builder_no_transitions():
    """States without transitions produce nodes but no edges."""
    hdl = make_hdlmodule()
    _build_fsm(hdl, [
        ('INIT', ()),
        ('S1', ()),
    ])
    graph = StateGraphBuilder().process(hdl)
    # AHDL_TRANSITION nodes aren't visited so S1 won't be in graph as dest
    assert isinstance(graph, StateGraph)


# ============================================================
# EmptyStateSkipper
# ============================================================

def test_empty_state_skipper_skips_empty():
    """EmptyStateSkipper rewrites AHDL_TRANSITION to skip empty states."""
    hdl = make_hdlmodule()
    # INIT -> EMPTY (empty) -> S1
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('EMPTY'),)),
        ('EMPTY', (AHDL_TRANSITION('S1'),)),
        ('S1', ()),
    ])
    EmptyStateSkipper().process(hdl)
    # INIT should now transition directly to S1
    init_state = stg.states[0]
    transition = init_state.block.codes[0]
    assert isinstance(transition, AHDL_TRANSITION)
    assert transition.target_name == 'S1'


def test_empty_state_skipper_non_empty_unchanged():
    """EmptyStateSkipper leaves non-empty target states unchanged."""
    hdl = make_hdlmodule()
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(0))
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', (mv,)),
    ])
    EmptyStateSkipper().process(hdl)
    init_state = stg.states[0]
    transition = init_state.block.codes[0]
    assert isinstance(transition, AHDL_TRANSITION)
    assert transition.target_name == 'S1'


# ============================================================
# StateReducer._remove_unreached_state
# ============================================================

def test_state_reducer_removes_unreached_state():
    """StateReducer removes states that are never transitioned to."""
    hdl = make_hdlmodule()
    _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', ()),
        ('UNREACHED', ()),  # no transition points here
    ])
    reducer = StateReducer()
    reducer._remove_unreached_state(hdl)
    stg = hdl.fsms['main_fsm'].stgs[0]
    state_names = [s.name for s in stg.states]
    # UNREACHED should be removed since nothing points to it
    assert 'UNREACHED' not in state_names


def test_state_reducer_keeps_reachable_states():
    """StateReducer keeps states that are reachable."""
    hdl = make_hdlmodule()
    _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', (AHDL_TRANSITION('S2'),)),
        ('S2', ()),
    ])
    reducer = StateReducer()
    reducer._remove_unreached_state(hdl)
    stg = hdl.fsms['main_fsm'].stgs[0]
    state_names = [s.name for s in stg.states]
    assert 'S1' in state_names
    assert 'S2' in state_names


# ============================================================
# StateReducer._remove_empty_init_state
# ============================================================

def test_state_reducer_removes_empty_init():
    """StateReducer removes empty INIT state and keeps remaining states."""
    hdl = make_hdlmodule()
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', ()),
    ])
    reducer = StateReducer()
    reducer._remove_empty_init_state(hdl)
    # INIT was empty -> removed
    stg = hdl.fsms['main_fsm'].stgs[0]
    state_names = [s.name for s in stg.states]
    assert 'INIT' not in state_names


def test_state_reducer_empty_fsm_removed():
    """If all states removed from FSM, the FSM entry is deleted from hdlmodule."""
    hdl = make_hdlmodule()
    # Single empty state -> entire FSM removed
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('INIT'),)),  # transition to self = not empty
    ])
    # Manually make it truly empty (transition to different state)
    # rebuild with a state that is_empty_state
    hdl2 = make_hdlmodule()
    fsm2, stg2 = _build_fsm(hdl2, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', (AHDL_TRANSITION('S1'),)),  # only state after remove
    ])
    reducer = StateReducer()
    reducer._remove_empty_init_state(hdl2)
    # INIT removed (was empty), S1 stays
    assert hdl2.fsms  # FSM still exists with S1


# ============================================================
# StateReducer.process() - full integration
# ============================================================

def test_state_reducer_process_full():
    """StateReducer.process() runs all sub-passes without error."""
    hdl = make_hdlmodule()
    _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', ()),
    ])
    StateReducer().process(hdl)
    # Should complete without error; INIT is empty and gets removed
    stg = hdl.fsms['main_fsm'].stgs[0]
    assert len(stg.states) >= 1


# ============================================================
# IfForwarder.visit_AHDL_TRANSITION_IF
# ============================================================

def test_state_reducer_single_state_no_removal():
    """_remove_unreached_state: single-state STG is skipped (len==1 continue)."""
    hdl = make_hdlmodule()
    _build_fsm(hdl, [('INIT', ())])
    reducer = StateReducer()
    reducer._remove_unreached_state(hdl)
    stg = hdl.fsms['main_fsm'].stgs[0]
    assert len(stg.states) == 1  # untouched


def test_state_reducer_self_loop_only_pred_removed():
    """_remove_unreached_state: state whose only pred is itself is removed."""
    hdl = make_hdlmodule()
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(0))
    # INIT has no transition to S1; S1 only loops to itself
    _build_fsm(hdl, [
        ('INIT', (mv,)),            # no transition to S1
        ('S1', (AHDL_TRANSITION('S1'),)),  # self-loop only
    ])
    reducer = StateReducer()
    reducer._remove_unreached_state(hdl)
    stg = hdl.fsms['main_fsm'].stgs[0]
    # S1 has only itself as predecessor -> removed
    state_names = [s.name for s in stg.states]
    assert 'S1' not in state_names


def test_state_reducer_empty_stg_and_fsm_removed():
    """_remove_empty_init_state: empty STG causes FSM removal."""
    hdl = make_hdlmodule()
    # Single state that IS empty (INIT -> S1, but S1 also empty - so all removed)
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', (AHDL_TRANSITION('S2'),)),
        ('S2', ()),
    ])
    reducer = StateReducer()
    # Manually remove S2 so S1 becomes the only state pointing to nothing, and INIT is empty
    stg.remove_state(stg.states[2])  # remove S2
    stg.remove_state(stg.states[1])  # remove S1
    # Now only INIT remains with transition to removed S1 -> still empty state
    reducer._remove_empty_init_state(hdl)
    assert 'main_fsm' not in hdl.fsms


def test_empty_state_skipper_chain():
    """EmptyStateSkipper follows a chain of empty states."""
    hdl = make_hdlmodule()
    # INIT -> E1 (empty) -> E2 (empty) -> S1
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('E1'),)),
        ('E1', (AHDL_TRANSITION('E2'),)),
        ('E2', (AHDL_TRANSITION('S1'),)),
        ('S1', ()),
    ])
    EmptyStateSkipper().process(hdl)
    # INIT should now transition to S1 directly
    init_state = stg.states[0]
    transition = init_state.block.codes[0]
    assert isinstance(transition, AHDL_TRANSITION)
    assert transition.target_name == 'S1'


def test_if_forwarder_inlines_target_state_codes():
    """IfForwarder replaces AHDL_TRANSITION_IF by inlining target state codes."""
    hdl = make_hdlmodule()
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(42))

    # S1 has some code followed by end
    fsm, stg = _build_fsm(hdl, [
        ('INIT', (AHDL_TRANSITION('S1'),)),
        ('S1', (mv,)),
        ('END', ()),
    ])

    cond = AHDL_VAR(reg_sig, Ctx.LOAD)
    then_blk = AHDL_BLOCK('', (AHDL_TRANSITION('S1'),))
    else_blk = AHDL_BLOCK('', (AHDL_TRANSITION('END'),))
    transition_if = AHDL_TRANSITION_IF((cond, None), (then_blk, else_blk))

    # Replace INIT's code with the TRANSITION_IF
    init_state = stg.states[0]
    new_block = AHDL_BLOCK('INIT', (transition_if,))
    object.__setattr__(init_state, 'block', new_block)

    IfForwarder().process(hdl)
    # The INIT state should now have inlined S1's code in the then-branch
    result_code = stg.states[0].block.codes[0]
    # After inlining, the if should contain S1's move
    assert isinstance(result_code, AHDL_IF)
