"""Tests for AHDLVarCollector covering all visit_* methods and accessor methods."""
from polyphony.compiler.ahdl.transformers.varcollector import AHDLVarCollector
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK,
    AHDL_CONST,
    AHDL_MEMVAR,
    AHDL_MOVE,
    AHDL_NOP,
    AHDL_VAR,
    State,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule, FSM
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

IR_SRC = """
scope test
tags function returnable
return int32

blk1:
ret @return
"""


def build_scope():
    setup_test()
    parser = IrReader(IR_SRC)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    assert scope is not None
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def make_stg_with_state(hdlmodule, stg_name='main', state_name='S0', codes=None):
    """Create a STG with a single state."""
    stg = STG(stg_name, None, hdlmodule)
    if codes is None:
        codes = (AHDL_NOP('nop'),)
    block = AHDL_BLOCK('blk', codes)
    state = stg.new_state(state_name, block, 0)
    stg.set_states([state])
    return stg, state


def add_fsm_with_stg(hdlmodule, fsm_name, stg_name='main', state_name='S0', codes=None):
    """Add an FSM with a single STG to hdlmodule and return (fsm, stg, state)."""
    scope = hdlmodule.scope
    hdlmodule.add_fsm(fsm_name, scope)
    stg, state = make_stg_with_state(hdlmodule, stg_name, state_name, codes)
    hdlmodule.add_fsm_stg(fsm_name, [stg])
    return hdlmodule.fsms[fsm_name], stg, state


# ============================================================
# Tests: process() initializes state correctly
# ============================================================

def test_process_initializes_empty_collections():
    """process() resets internal dicts to empty defaultdicts."""
    hdl = make_hdlmodule()
    collector = AHDLVarCollector()
    collector.process(hdl)
    assert len(collector._defs) == 0
    assert len(collector._uses) == 0
    assert len(collector._outputs) == 0
    assert len(collector._mems) == 0


def test_process_with_empty_hdlmodule_runs_without_error():
    """process() on a module with no FSMs or decls does not raise."""
    hdl = make_hdlmodule()
    collector = AHDLVarCollector()
    collector.process(hdl)  # must not raise


# ============================================================
# Tests: visit_AHDL_VAR — def/use classification
# ============================================================

def test_var_store_goes_to_defs():
    """AHDL_VAR with Ctx.STORE is recorded in _defs under the FSM name."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('reg_dst', 8, {'reg'})
    dst = AHDL_VAR(sig, Ctx.STORE)
    src = AHDL_CONST(0)
    move = AHDL_MOVE(dst, src)
    fsm, stg, state = add_fsm_with_stg(hdl, 'fsm_def', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig,) in collector.def_vars('fsm_def')


def test_var_load_goes_to_uses():
    """AHDL_VAR with Ctx.LOAD is recorded in _uses under the FSM name."""
    hdl = make_hdlmodule()
    sig_dst = hdl.gen_sig('dst_u', 8, {'reg'})
    sig_src = hdl.gen_sig('src_u', 8, {'reg'})
    dst = AHDL_VAR(sig_dst, Ctx.STORE)
    src = AHDL_VAR(sig_src, Ctx.LOAD)
    move = AHDL_MOVE(dst, src)
    add_fsm_with_stg(hdl, 'fsm_use', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig_src,) in collector.use_vars('fsm_use')


# ============================================================
# Tests: visit_AHDL_VAR — output_vars classification
# ============================================================

def test_output_sig_added_to_outputs():
    """AHDL_VAR with 'output' tag is added to output_vars."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('out_sig', 8, {'output'})
    dst = AHDL_VAR(sig, Ctx.STORE)
    src = AHDL_CONST(0)
    move = AHDL_MOVE(dst, src)
    add_fsm_with_stg(hdl, 'fsm_out', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig,) in collector.output_vars('fsm_out')


def test_input_single_port_sig_added_to_outputs():
    """AHDL_VAR with 'input' + 'single_port' tags is added to output_vars."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('inp_sp', 8, {'input', 'single_port'})
    dst = AHDL_VAR(sig, Ctx.STORE)
    src = AHDL_CONST(0)
    move = AHDL_MOVE(dst, src)
    add_fsm_with_stg(hdl, 'fsm_inp_sp', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig,) in collector.output_vars('fsm_inp_sp')


def test_input_without_single_port_not_in_outputs():
    """AHDL_VAR with 'input' but NOT 'single_port' is NOT in output_vars."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('inp_no_sp', 8, {'input'})
    dst = AHDL_VAR(sig, Ctx.STORE)
    src = AHDL_CONST(0)
    move = AHDL_MOVE(dst, src)
    add_fsm_with_stg(hdl, 'fsm_inp_no_sp', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig,) not in collector.output_vars('fsm_inp_no_sp')


def test_ctrl_sig_not_added_to_outputs():
    """AHDL_VAR with 'ctrl' tag is never added to output_vars."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('ctrl_sig', 1, {'ctrl', 'reg'})
    dst = AHDL_VAR(sig, Ctx.STORE)
    src = AHDL_CONST(0)
    move = AHDL_MOVE(dst, src)
    add_fsm_with_stg(hdl, 'fsm_ctrl', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig,) not in collector.output_vars('fsm_ctrl')


def test_plain_reg_not_added_to_outputs():
    """AHDL_VAR with only 'reg' tag (not output/input/ctrl) is not in output_vars."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('plain_reg', 8, {'reg'})
    dst = AHDL_VAR(sig, Ctx.STORE)
    src = AHDL_CONST(0)
    move = AHDL_MOVE(dst, src)
    add_fsm_with_stg(hdl, 'fsm_plain', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig,) not in collector.output_vars('fsm_plain')


# ============================================================
# Tests: visit_AHDL_MEMVAR
# ============================================================

def test_memvar_store_goes_to_defs_and_mems():
    """AHDL_MEMVAR with Ctx.STORE is in _defs and _mems."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('mem_dst', (8, 4), {'regarray'})
    memvar = AHDL_MEMVAR(sig, Ctx.STORE)
    src = AHDL_CONST(0)
    from polyphony.compiler.ahdl.ahdl import AHDL_SUBSCRIPT
    subscript_dst = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    move = AHDL_MOVE(subscript_dst, src)
    add_fsm_with_stg(hdl, 'fsm_mem_def', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig,) in collector.def_vars('fsm_mem_def')
    assert (sig,) in collector.mem_vars('fsm_mem_def')


def test_memvar_load_goes_to_uses_and_mems():
    """AHDL_MEMVAR with Ctx.LOAD is in _uses and _mems."""
    hdl = make_hdlmodule()
    sig_mem = hdl.gen_sig('mem_src', (8, 4), {'regarray'})
    sig_dst = hdl.gen_sig('dst_m2', 8, {'reg'})
    memvar = AHDL_MEMVAR(sig_mem, Ctx.LOAD)
    from polyphony.compiler.ahdl.ahdl import AHDL_SUBSCRIPT
    src = AHDL_SUBSCRIPT(memvar, AHDL_CONST(0))
    dst = AHDL_VAR(sig_dst, Ctx.STORE)
    move = AHDL_MOVE(dst, src)
    add_fsm_with_stg(hdl, 'fsm_mem_use', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig_mem,) in collector.use_vars('fsm_mem_use')
    assert (sig_mem,) in collector.mem_vars('fsm_mem_use')


# ============================================================
# Tests: current_fsm is None (no FSM context) — tag is ''
# ============================================================

def test_var_in_decl_context_uses_empty_tag():
    """AHDL_VAR visited outside an FSM (via decl) uses '' as the tag."""
    hdl = make_hdlmodule()
    sig_dst = hdl.gen_sig('decl_dst', 8, {'net'})
    sig_src = hdl.gen_sig('decl_src', 8, {'reg'})
    from polyphony.compiler.ahdl.ahdl import AHDL_ASSIGN
    dst = AHDL_VAR(sig_dst, Ctx.STORE)
    src = AHDL_VAR(sig_src, Ctx.LOAD)
    assign = AHDL_ASSIGN(dst, src)
    hdl.add_decl(assign)

    collector = AHDLVarCollector()
    collector.process(hdl)

    # Both vars should be keyed under '' (no FSM)
    assert (sig_dst,) in collector.def_vars('')
    assert (sig_src,) in collector.use_vars('')


# ============================================================
# Tests: accessor methods
# ============================================================

def test_def_vars_returns_set():
    """def_vars() returns a set of var tuples for the given FSM name."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('dv_sig', 8, {'reg'})
    move = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(0))
    add_fsm_with_stg(hdl, 'fsm_dv', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.def_vars('fsm_dv')
    assert isinstance(result, set)
    assert (sig,) in result


def test_use_vars_returns_set():
    """use_vars() returns a set of var tuples for the given FSM name."""
    hdl = make_hdlmodule()
    sig_dst = hdl.gen_sig('uv_dst', 8, {'reg'})
    sig_src = hdl.gen_sig('uv_src', 8, {'reg'})
    move = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_VAR(sig_src, Ctx.LOAD))
    add_fsm_with_stg(hdl, 'fsm_uv', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.use_vars('fsm_uv')
    assert isinstance(result, set)
    assert (sig_src,) in result


def test_output_vars_returns_set():
    """output_vars() returns a set of var tuples for the given FSM name."""
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('ov_sig', 8, {'output'})
    move = AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), AHDL_CONST(0))
    add_fsm_with_stg(hdl, 'fsm_ov', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.output_vars('fsm_ov')
    assert isinstance(result, set)
    assert (sig,) in result


def test_mem_vars_returns_set():
    """mem_vars() returns a set of memvar tuples for the given FSM name."""
    hdl = make_hdlmodule()
    sig_mem = hdl.gen_sig('mv_mem', (8, 4), {'regarray'})
    sig_dst = hdl.gen_sig('mv_dst', 8, {'reg'})
    memvar = AHDL_MEMVAR(sig_mem, Ctx.LOAD)
    from polyphony.compiler.ahdl.ahdl import AHDL_SUBSCRIPT
    move = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), AHDL_SUBSCRIPT(memvar, AHDL_CONST(0)))
    add_fsm_with_stg(hdl, 'fsm_mv', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.mem_vars('fsm_mv')
    assert isinstance(result, set)
    assert (sig_mem,) in result


# ============================================================
# Tests: submodule_def_vars / submodule_use_vars / submodule_vars
# ============================================================

def test_submodule_def_vars_no_fsm_name_returns_multi_signal_vars():
    """submodule_def_vars(None) returns only var tuples with len > 1 across all FSMs."""
    hdl = make_hdlmodule()
    sig1 = hdl.gen_sig('sub_a', 8, {'reg'})
    sig2 = hdl.gen_sig('sub_b', 8, {'reg'})
    sig_single = hdl.gen_sig('single_s', 8, {'reg'})

    # Create a 2-element var tuple (simulates submodule access: module.signal)
    multi_var = AHDL_VAR((sig1, sig2), Ctx.STORE)
    single_var = AHDL_VAR(sig_single, Ctx.STORE)
    move_multi = AHDL_MOVE(multi_var, AHDL_CONST(0))
    move_single = AHDL_MOVE(single_var, AHDL_CONST(0))

    add_fsm_with_stg(hdl, 'fsm_sub', codes=(move_multi, move_single))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.submodule_def_vars()
    assert (sig1, sig2) in result
    assert (sig_single,) not in result


def test_submodule_def_vars_with_fsm_name_filters_by_fsm():
    """submodule_def_vars(fsm_name) filters by the given FSM."""
    hdl = make_hdlmodule()
    sig1 = hdl.gen_sig('sub_f1', 8, {'reg'})
    sig2 = hdl.gen_sig('sub_f2', 8, {'reg'})
    multi_var = AHDL_VAR((sig1, sig2), Ctx.STORE)
    move = AHDL_MOVE(multi_var, AHDL_CONST(0))
    add_fsm_with_stg(hdl, 'fsm_filter', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result_with_name = collector.submodule_def_vars('fsm_filter')
    result_with_other = collector.submodule_def_vars('other_fsm')

    assert (sig1, sig2) in result_with_name
    assert len(result_with_other) == 0


def test_submodule_use_vars_no_fsm_name_returns_multi_signal_vars():
    """submodule_use_vars(None) returns only use var tuples with len > 1."""
    hdl = make_hdlmodule()
    sig1 = hdl.gen_sig('usub_a', 8, {'reg'})
    sig2 = hdl.gen_sig('usub_b', 8, {'reg'})
    sig_dst = hdl.gen_sig('usub_dst', 8, {'reg'})

    multi_var = AHDL_VAR((sig1, sig2), Ctx.LOAD)
    move = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), multi_var)
    add_fsm_with_stg(hdl, 'fsm_usub', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.submodule_use_vars()
    assert (sig1, sig2) in result


def test_submodule_use_vars_with_fsm_name():
    """submodule_use_vars(fsm_name) only includes vars from that FSM."""
    hdl = make_hdlmodule()
    sig1 = hdl.gen_sig('usub_f1', 8, {'reg'})
    sig2 = hdl.gen_sig('usub_f2', 8, {'reg'})
    sig_dst = hdl.gen_sig('usub_fdst', 8, {'reg'})
    multi_var = AHDL_VAR((sig1, sig2), Ctx.LOAD)
    move = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), multi_var)
    add_fsm_with_stg(hdl, 'fsm_uf', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    assert (sig1, sig2) in collector.submodule_use_vars('fsm_uf')
    assert len(collector.submodule_use_vars('no_such_fsm')) == 0


def test_submodule_vars_is_union_of_def_and_use():
    """submodule_vars() returns the union of submodule_def_vars and submodule_use_vars."""
    hdl = make_hdlmodule()
    sig_da = hdl.gen_sig('sv_da', 8, {'reg'})
    sig_db = hdl.gen_sig('sv_db', 8, {'reg'})
    sig_ua = hdl.gen_sig('sv_ua', 8, {'reg'})
    sig_ub = hdl.gen_sig('sv_ub', 8, {'reg'})
    sig_dst = hdl.gen_sig('sv_dst', 8, {'reg'})

    def_multi = AHDL_VAR((sig_da, sig_db), Ctx.STORE)
    use_multi = AHDL_VAR((sig_ua, sig_ub), Ctx.LOAD)
    move1 = AHDL_MOVE(def_multi, AHDL_CONST(0))
    move2 = AHDL_MOVE(AHDL_VAR(sig_dst, Ctx.STORE), use_multi)
    add_fsm_with_stg(hdl, 'fsm_sv', codes=(move1, move2))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.submodule_vars()
    assert (sig_da, sig_db) in result
    assert (sig_ua, sig_ub) in result


def test_submodule_vars_with_fsm_name():
    """submodule_vars(fsm_name) filters both def and use by that FSM."""
    hdl = make_hdlmodule()
    sig1 = hdl.gen_sig('svf_a', 8, {'reg'})
    sig2 = hdl.gen_sig('svf_b', 8, {'reg'})
    multi_var = AHDL_VAR((sig1, sig2), Ctx.STORE)
    move = AHDL_MOVE(multi_var, AHDL_CONST(0))
    add_fsm_with_stg(hdl, 'fsm_svf', codes=(move,))

    collector = AHDLVarCollector()
    collector.process(hdl)

    result = collector.submodule_vars('fsm_svf')
    assert (sig1, sig2) in result
    assert len(collector.submodule_vars('nonexistent')) == 0
