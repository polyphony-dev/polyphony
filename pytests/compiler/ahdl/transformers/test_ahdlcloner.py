"""Tests for AHDLCloner covering uncovered lines."""
from polyphony.compiler.ahdl.transformers.ahdlcloner import AHDLCloner
from polyphony.compiler.ahdl.ahdl import (
    AHDL_VAR, AHDL_MEMVAR, AHDL_MOVE, AHDL_CONST, AHDL_BLOCK, AHDL_EVENT_TASK,
    Ctx,
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


def test_cloner_memvar_remapped():
    """visit_AHDL_MEMVAR: when scope is not namespace, signals are remapped via sig_maps."""
    hdl = make_hdlmodule()
    arr_sig = hdl.gen_sig('arr', 8, {'reg'})
    new_arr = hdl.gen_sig('arr_new', 8, {'reg'})
    sig_maps = {hdl.name: {arr_sig: new_arr}}

    cloner = AHDLCloner(sig_maps)
    cloner.hdlmodule = hdl
    memvar = AHDL_MEMVAR(arr_sig, Ctx.LOAD)
    result = cloner.visit_AHDL_MEMVAR(memvar)

    assert isinstance(result, AHDL_MEMVAR)
    assert result.vars[0] is new_arr


def test_cloner_event_task_remapped():
    """visit_AHDL_EVENT_TASK: events are remapped via sig_maps."""
    hdl = make_hdlmodule()
    clk_sig = hdl.gen_sig('clk', 1, {'reg'})
    new_clk = hdl.gen_sig('clk2', 1, {'reg'})
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    new_reg = hdl.gen_sig('r2', 8, {'reg'})

    sig_maps = {hdl.name: {clk_sig: new_clk, reg_sig: new_reg}}
    stm = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(0))
    task = AHDL_EVENT_TASK(((clk_sig, 'rising'),), stm)

    cloner = AHDLCloner(sig_maps)
    cloner.hdlmodule = hdl
    result = cloner.visit_AHDL_EVENT_TASK(task)

    assert isinstance(result, AHDL_EVENT_TASK)
    assert result.events[0][0] is new_clk
    assert result.events[0][1] == 'rising'


def test_cloner_process_with_tasks():
    """AHDLCloner.process() remaps signals in tasks (covers EVENT_TASK via process)."""
    hdl = make_hdlmodule()
    clk_sig = hdl.gen_sig('clk', 1, {'reg'})
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    new_clk = hdl.gen_sig('clk_cloned', 1, {'reg'})
    new_reg = hdl.gen_sig('r_cloned', 8, {'reg'})

    stm = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(0))
    task = AHDL_EVENT_TASK(((clk_sig, 'rising'),), stm)
    hdl.tasks.append(task)

    sig_maps = {hdl.name: {clk_sig: new_clk, reg_sig: new_reg}}
    AHDLCloner(sig_maps).process(hdl)

    new_task = hdl.tasks[0]
    assert isinstance(new_task, AHDL_EVENT_TASK)
    assert new_task.events[0][0] is new_clk


def test_cloner_process_with_memvar_in_fsm():
    """AHDLCloner.process() remaps AHDL_VAR signals inside FSM states."""
    hdl = make_hdlmodule()
    arr_sig = hdl.gen_sig('arr', 8, {'reg'})
    new_arr = hdl.gen_sig('arr_cloned', 8, {'reg'})

    state_sig = hdl.gen_sig('fsm_state', 4, {'reg'})
    fsm = FSM('main_fsm', hdl.scope, state_sig)
    stg = STG('main', None, hdl)

    mv = AHDL_MOVE(AHDL_VAR(arr_sig, Ctx.STORE), AHDL_CONST(1))
    block = AHDL_BLOCK('INIT', (mv,))
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['main_fsm'] = fsm

    sig_maps = {hdl.name: {arr_sig: new_arr, state_sig: state_sig}}
    AHDLCloner(sig_maps).process(hdl)

    new_state = hdl.fsms['main_fsm'].stgs[0].states[0]
    mv_result = new_state.block.codes[0]
    assert isinstance(mv_result, AHDL_MOVE)
    assert mv_result.dst.sig is new_arr
