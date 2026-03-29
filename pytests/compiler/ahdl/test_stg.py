"""Tests for STG class covering uncovered lines."""
from polyphony.compiler.ahdl.ahdl import AHDL_BLOCK, State
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope():
    setup_test()
    src = '''
scope test
tags function returnable
'''
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def test_stg_str():
    hdl = make_hdlmodule()
    stg = STG('main', None, hdl)
    block = AHDL_BLOCK('', ())
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    s = str(stg)
    assert isinstance(s, str)


def test_stg_remove_state():
    hdl = make_hdlmodule()
    stg = STG('main', None, hdl)
    block = AHDL_BLOCK('', ())
    state1 = stg.new_state('S1', block, 0)
    state2 = stg.new_state('S2', block, 1)
    stg.set_states([state1, state2])
    assert len(stg.states) == 2
    stg.remove_state(state1)
    assert len(stg.states) == 1
    assert not stg.has_state('S1')
    assert stg.has_state('S2')
