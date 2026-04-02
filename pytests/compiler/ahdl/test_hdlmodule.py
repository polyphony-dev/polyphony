"""Tests covering uncovered lines in polyphony/compiler/ahdl/hdlmodule.py."""
import pytest
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_MOVE, AHDL_NOP, AHDL_VAR, AHDL_ASSIGN,
    AHDL_FUNCTION, AHDL_EVENT_TASK, State,
)
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ahdl.hdlmodule import HDLModule, FSM
from polyphony.compiler.ahdl.hdlscope import HDLScope
from polyphony.compiler.ir.ir import Ctx
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_reg_var(hdl, name, width=8):
    sig = hdl.gen_sig(name, width, {'reg'})
    return AHDL_VAR(sig, Ctx.STORE)


def _make_net_var(hdl, name, width=8):
    sig = hdl.gen_sig(name, width, {'net'})
    return AHDL_VAR(sig, Ctx.STORE)


def _make_input_var(hdl, name, width=8):
    sig = hdl.gen_sig(name, width, {'input', 'reg'})
    return AHDL_VAR(sig, Ctx.STORE)


def _make_output_var(hdl, name, width=8):
    sig = hdl.gen_sig(name, width, {'output', 'net'})
    return AHDL_VAR(sig, Ctx.STORE)


def _make_assign(hdl, dst_name, src_value=0):
    dst_sig = hdl.gen_sig(dst_name, 8, {'net'})
    dst_var = AHDL_VAR(dst_sig, Ctx.STORE)
    src = AHDL_CONST(src_value)
    return AHDL_ASSIGN(dst_var, src)


def _make_stg(hdl, name, parent=None, num_states=1):
    stg = STG(name, parent, hdl)
    block = AHDL_BLOCK('', ())
    states = []
    for i in range(num_states):
        state = stg.new_state(f'{name}_S{i}', block, i)
        states.append(state)
    stg.set_states(states)
    return stg


# ---------------------------------------------------------------------------
# FSM tests
# ---------------------------------------------------------------------------

class TestFSM:
    def test_clone(self):
        """FSM.clone() copies outputs and reset_stms; stgs are handled by the caller."""
        hdl = make_hdlmodule()
        state_sig = hdl.gen_sig('fsm_state', -1, {'reg'})
        scope = hdl.scope
        fsm = FSM('myfsm', scope, state_sig)

        # Keep stgs empty so that the stg.clone() call is not triggered
        # (STG does not implement clone(); that code path is guarded by the list comprehension)
        out_sig = hdl.gen_sig('out1', 8, {'net', 'output'})
        fsm.outputs.add(out_sig)
        nop = AHDL_NOP('reset')
        fsm.reset_stms.append(nop)

        cloned = fsm.clone()

        assert cloned is not fsm
        assert cloned.name == fsm.name
        assert cloned.scope is fsm.scope
        assert cloned.state_var is fsm.state_var
        assert out_sig in cloned.outputs
        assert cloned.outputs is not fsm.outputs  # copy
        assert len(cloned.reset_stms) == 1
        assert cloned.reset_stms is not fsm.reset_stms  # shallow copy (slice)

    def test_remove_stg_non_main(self):
        """Removing a non-main (child) STG does not touch other stg parents."""
        hdl = make_hdlmodule()
        state_sig = hdl.gen_sig('fsm2_state', -1, {'reg'})
        fsm = FSM('fsm2', hdl.scope, state_sig)

        main_stg = _make_stg(hdl, 'main')
        child_stg = _make_stg(hdl, 'child', parent=main_stg)
        fsm.stgs = [main_stg, child_stg]

        # Remove child (non-main), parent pointers should be untouched
        fsm.remove_stg(child_stg)
        assert child_stg not in fsm.stgs
        assert main_stg in fsm.stgs
        # main_stg is the parent of removed child; nothing should be cleared
        # (the branch `if stg.is_main()` is NOT taken here)

    def test_remove_stg_main_clears_child_parents(self):
        """Removing the main STG sets child stg parents to None."""
        hdl = make_hdlmodule()
        state_sig = hdl.gen_sig('fsm3_state', -1, {'reg'})
        fsm = FSM('fsm3', hdl.scope, state_sig)

        main_stg = _make_stg(hdl, 'main')
        child_stg = _make_stg(hdl, 'child', parent=main_stg)
        fsm.stgs = [main_stg, child_stg]

        # Remove main STG: child's parent should be set to None
        fsm.remove_stg(main_stg)
        assert main_stg not in fsm.stgs
        assert child_stg in fsm.stgs
        assert child_stg.parent is None


# ---------------------------------------------------------------------------
# HDLModule.is_hdlmodule_scope tests
# ---------------------------------------------------------------------------

class TestIsHdlmoduleScope:
    def test_function_module(self):
        """A function-module scope returns True."""
        scope = build_scope()
        # 'function returnable' tags => is_function_module() may be True
        # Test the classmethod directly with a mock that reports is_function_module
        class FakeScope:
            def is_module(self): return False
            def is_top_module(self): return False
            def is_instantiated(self): return False
            def is_function_module(self): return True
            def is_testbench(self): return False
        assert HDLModule.is_hdlmodule_scope(FakeScope()) is True

    def test_top_instantiated(self):
        class FakeScope:
            def is_module(self): return True
            def is_top_module(self): return True
            def is_instantiated(self): return True
            def is_function_module(self): return False
            def is_testbench(self): return False
        assert HDLModule.is_hdlmodule_scope(FakeScope()) is True

    def test_testbench(self):
        class FakeScope:
            def is_module(self): return False
            def is_top_module(self): return False
            def is_instantiated(self): return False
            def is_function_module(self): return False
            def is_testbench(self): return True
        assert HDLModule.is_hdlmodule_scope(FakeScope()) is True

    def test_plain_scope_is_false(self):
        class FakeScope:
            def is_module(self): return False
            def is_top_module(self): return False
            def is_instantiated(self): return False
            def is_function_module(self): return False
            def is_testbench(self): return False
        assert HDLModule.is_hdlmodule_scope(FakeScope()) is False

    def test_top_not_instantiated_is_false(self):
        class FakeScope:
            def is_module(self): return True
            def is_top_module(self): return True
            def is_instantiated(self): return False
            def is_function_module(self): return False
            def is_testbench(self): return False
        assert HDLModule.is_hdlmodule_scope(FakeScope()) is False


# ---------------------------------------------------------------------------
# HDLModule basic attribute management
# ---------------------------------------------------------------------------

class TestHDLModuleBasicMethods:
    def test_add_and_get_inputs(self):
        hdl = make_hdlmodule()
        var = _make_input_var(hdl, 'in_a')
        hdl.add_input(var)
        assert var in hdl.inputs()

    def test_add_and_get_outputs(self):
        hdl = make_hdlmodule()
        var = _make_output_var(hdl, 'out_a')
        hdl.add_output(var)
        assert var in hdl.outputs()

    def test_inputs_returns_list(self):
        hdl = make_hdlmodule()
        result = hdl.inputs()
        assert isinstance(result, list)

    def test_outputs_returns_list(self):
        hdl = make_hdlmodule()
        result = hdl.outputs()
        assert isinstance(result, list)

    def test_add_task(self):
        hdl = make_hdlmodule()
        clk_sig = hdl.gen_sig('clk', 1, {'net'})
        nop = AHDL_NOP('task_body')
        task = AHDL_EVENT_TASK(((clk_sig, 'posedge'),), nop)
        hdl.add_task(task)
        assert task in hdl.tasks

    def test_add_constant(self):
        hdl = make_hdlmodule()
        hdl.add_constant('MY_CONST', 42)
        names = [sig.name for sig in hdl.constants.keys()]
        assert 'MY_CONST' in names
        values = list(hdl.constants.values())
        assert 42 in values

    def test_add_constant_adds_to_signals(self):
        hdl = make_hdlmodule()
        hdl.add_constant('CONST_B', 7)
        assert 'CONST_B' in hdl.signals

    def test_add_static_assignment(self):
        hdl = make_hdlmodule()
        assign = _make_assign(hdl, 'sa_dst')
        hdl.add_static_assignment(assign)
        assert assign in hdl.decls

    def test_add_static_assignment_requires_ahdl_assign(self):
        hdl = make_hdlmodule()
        nop = AHDL_NOP('bad')
        with pytest.raises((AssertionError, Exception)):
            hdl.add_static_assignment(nop)  # type: ignore

    def test_get_static_assignment(self):
        hdl = make_hdlmodule()
        assign = _make_assign(hdl, 'gs_dst')
        hdl.add_static_assignment(assign)
        assigns = hdl.get_static_assignment()
        assert assign in assigns
        assert all(isinstance(a, AHDL_ASSIGN) for a in assigns)

    def test_get_static_assignment_empty(self):
        hdl = make_hdlmodule()
        assert hdl.get_static_assignment() == []

    def test_add_decl_deduplication(self):
        hdl = make_hdlmodule()
        assign = _make_assign(hdl, 'dup_dst')
        hdl.add_decl(assign)
        hdl.add_decl(assign)  # duplicate — should not be added twice
        assert hdl.decls.count(assign) == 1

    def test_add_decl_requires_ahdl_decl(self):
        hdl = make_hdlmodule()
        with pytest.raises(AssertionError):
            hdl.add_decl(AHDL_NOP('bad'))  # type: ignore

    def test_remove_decl(self):
        hdl = make_hdlmodule()
        assign = _make_assign(hdl, 'rm_dst')
        hdl.add_decl(assign)
        assert assign in hdl.decls
        hdl.remove_decl(assign)
        assert assign not in hdl.decls

    def test_remove_decl_requires_ahdl_decl(self):
        hdl = make_hdlmodule()
        with pytest.raises(AssertionError):
            hdl.remove_decl(AHDL_NOP('bad'))  # type: ignore

    def test_add_sub_module(self):
        hdl = make_hdlmodule()
        sub_hdl = make_hdlmodule()
        sig1 = hdl.gen_sig('port_a', 8, {'input'})
        sig2 = sub_hdl.gen_sig('port_b', 8, {'output'})
        var1 = AHDL_VAR(sig1, Ctx.LOAD)
        hdl.add_sub_module('sub_inst', sub_hdl, [(sig1, sig2)], {'PARAM': 1})
        assert 'sub_inst' in hdl.sub_modules
        name, mod, conns, params = hdl.sub_modules['sub_inst']
        assert name == 'sub_inst'
        assert mod is sub_hdl
        assert params == {'PARAM': 1}

    def test_add_sub_module_no_param_map(self):
        hdl = make_hdlmodule()
        sub_hdl = make_hdlmodule()
        hdl.add_sub_module('sub2', sub_hdl, [])
        assert 'sub2' in hdl.sub_modules

    def test_add_function(self):
        hdl = make_hdlmodule()
        out_sig = hdl.gen_sig('func_out', 8, {'net'})
        out_var = AHDL_VAR(out_sig, Ctx.STORE)
        func = AHDL_FUNCTION(out_var, (), ())
        hdl.add_function(func)
        assert func in hdl.functions

    def test_add_function_requires_ahdl_function(self):
        hdl = make_hdlmodule()
        with pytest.raises(AssertionError):
            hdl.add_function(AHDL_NOP('bad'))  # type: ignore

    def test_add_edge_detector(self):
        hdl = make_hdlmodule()
        sig = hdl.gen_sig('edge_sig', 1, {'net'})
        var = AHDL_VAR(sig, Ctx.LOAD)
        old_val = AHDL_CONST(0)
        new_val = AHDL_CONST(1)
        hdl.add_edge_detector(var, old_val, new_val)
        assert (var, old_val, new_val) in hdl.edge_detectors


# ---------------------------------------------------------------------------
# FSM management
# ---------------------------------------------------------------------------

class TestFSMManagement:
    def test_add_fsm(self):
        hdl = make_hdlmodule()
        hdl.add_fsm('myfsm', hdl.scope)
        assert 'myfsm' in hdl.fsms
        fsm = hdl.fsms['myfsm']
        assert fsm.name == 'myfsm'
        assert 'myfsm_state' in hdl.signals

    def test_add_fsm_stg(self):
        hdl = make_hdlmodule()
        hdl.add_fsm('fsm1', hdl.scope)
        stg = _make_stg(hdl, 'main')
        hdl.add_fsm_stg('fsm1', [stg])
        assert stg in hdl.fsms['fsm1'].stgs
        assert stg.fsm is hdl.fsms['fsm1']

    def test_add_fsm_output(self):
        hdl = make_hdlmodule()
        hdl.add_fsm('fsm2', hdl.scope)
        out_sig = hdl.gen_sig('fsm2_out', 8, {'net', 'output'})
        hdl.add_fsm_output('fsm2', out_sig)
        assert out_sig in hdl.fsms['fsm2'].outputs

    def test_add_fsm_output_asserts_fsm_exists(self):
        hdl = make_hdlmodule()
        sig = hdl.gen_sig('ghost_out', 8, {'net'})
        with pytest.raises(AssertionError):
            hdl.add_fsm_output('nonexistent', sig)

    def test_add_fsm_reset_stm(self):
        hdl = make_hdlmodule()
        hdl.add_fsm('fsm3', hdl.scope)
        nop = AHDL_NOP('reset')
        hdl.add_fsm_reset_stm('fsm3', nop)
        assert nop in hdl.fsms['fsm3'].reset_stms

    def test_add_fsm_reset_stm_asserts_fsm_exists(self):
        hdl = make_hdlmodule()
        with pytest.raises(AssertionError):
            hdl.add_fsm_reset_stm('nonexistent', AHDL_NOP('x'))


# ---------------------------------------------------------------------------
# resources()
# ---------------------------------------------------------------------------

class TestResources:
    def test_resources_empty(self):
        hdl = make_hdlmodule()
        regs, nets, states = hdl.resources()
        assert regs == 0
        assert nets == 0
        assert states == 0

    def test_resources_with_reg(self):
        hdl = make_hdlmodule()
        hdl.gen_sig('r1', 16, {'reg'})
        regs, nets, states = hdl.resources()
        assert regs == 16
        assert nets == 0

    def test_resources_with_net(self):
        hdl = make_hdlmodule()
        hdl.gen_sig('n1', 8, {'net'})
        regs, nets, states = hdl.resources()
        assert regs == 0
        assert nets == 8

    def test_resources_ignores_input_output(self):
        hdl = make_hdlmodule()
        hdl.gen_sig('inp', 8, {'input', 'reg'})
        hdl.gen_sig('out', 8, {'output', 'net'})
        regs, nets, states = hdl.resources()
        assert regs == 0
        assert nets == 0

    def test_resources_with_regarray(self):
        hdl = make_hdlmodule()
        hdl.gen_sig('ra', (4, 3), {'regarray'})  # width=4, length=3 => 12 bits
        regs, nets, states = hdl.resources()
        assert regs == 12

    def test_resources_with_netarray(self):
        hdl = make_hdlmodule()
        hdl.gen_sig('na', (2, 5), {'netarray'})  # width=2, length=5 => 10 bits
        _, nets, _ = hdl.resources()
        assert nets == 10

    def test_resources_with_negative_width_reg_skipped(self):
        """State sigs have width=-1 and should not add to reg count."""
        hdl = make_hdlmodule()
        hdl.gen_sig('state_sig', -1, {'reg'})
        regs, _, _ = hdl.resources()
        assert regs == 0

    def test_resources_counts_states_in_fsm(self):
        hdl = make_hdlmodule()
        hdl.add_fsm('count_fsm', hdl.scope)
        stg = _make_stg(hdl, 'main', num_states=3)
        hdl.add_fsm_stg('count_fsm', [stg])
        _, _, states = hdl.resources()
        assert states == 3

    def test_resources_multiple_stgs(self):
        hdl = make_hdlmodule()
        hdl.add_fsm('mfsm', hdl.scope)
        stg1 = _make_stg(hdl, 'stg1', num_states=2)
        stg2 = _make_stg(hdl, 'stg2', num_states=4)
        hdl.add_fsm_stg('mfsm', [stg1, stg2])
        _, _, states = hdl.resources()
        assert states == 6


# ---------------------------------------------------------------------------
# connectors()
# ---------------------------------------------------------------------------

class TestConnectors:
    def test_connector_input_attrs(self):
        """Input connectors should have 'connector', 'reg', 'initializable'."""
        hdl = make_hdlmodule()
        in_sig = hdl.gen_sig('test_in_a', 8, {'input', 'reg'})
        in_var = AHDL_VAR(in_sig, Ctx.STORE)
        hdl.add_input(in_var)

        results = list(hdl.connectors('inst'))
        assert len(results) == 1
        var, connector_name, attr = results[0]
        assert 'connector' in attr
        assert 'reg' in attr
        assert 'initializable' in attr
        assert 'net' not in attr

    def test_connector_output_attrs(self):
        """Output connectors should have 'connector', 'net'."""
        hdl = make_hdlmodule()
        out_sig = hdl.gen_sig('test_out_b', 8, {'output', 'net'})
        out_var = AHDL_VAR(out_sig, Ctx.STORE)
        hdl.add_output(out_var)

        results = list(hdl.connectors('inst'))
        assert len(results) == 1
        var, connector_name, attr = results[0]
        assert 'connector' in attr
        assert 'net' in attr
        assert 'reg' not in attr

    def test_connector_ctrl_signal(self):
        """Ctrl signals add 'ctrl' to attr."""
        hdl = make_hdlmodule()
        ctrl_sig = hdl.gen_sig('test_ctrl_c', 1, {'input', 'reg', 'ctrl'})
        ctrl_var = AHDL_VAR(ctrl_sig, Ctx.STORE)
        hdl.add_input(ctrl_var)

        results = list(hdl.connectors('inst'))
        assert len(results) == 1
        _, _, attr = results[0]
        assert 'ctrl' in attr

    def test_connector_name_non_module_scope(self):
        """For non-module scopes, connector_name is derived from var.name minus scope prefix."""
        hdl = make_hdlmodule()
        # The scope base_name is 'test' for our test scope
        # Signal name should start with scope base_name + '_'
        in_sig = hdl.gen_sig('test_port_x', 8, {'input', 'reg'})
        in_var = AHDL_VAR(in_sig, Ctx.STORE)
        hdl.add_input(in_var)

        results = list(hdl.connectors('inst'))
        _, connector_name, _ = results[0]
        # connector_name = prefix + '_' + ifname
        # ifname = var.name[len(scope.base_name)+1:] = 'test_port_x'[5:] = 'port_x'
        assert connector_name == 'inst_port_x'

    def test_connector_empty(self):
        hdl = make_hdlmodule()
        assert list(hdl.connectors('p')) == []

    def test_connector_both_input_output(self):
        hdl = make_hdlmodule()
        in_sig = hdl.gen_sig('test_in_io', 8, {'input', 'reg'})
        out_sig = hdl.gen_sig('test_out_io', 8, {'output', 'net'})
        hdl.add_input(AHDL_VAR(in_sig, Ctx.STORE))
        hdl.add_output(AHDL_VAR(out_sig, Ctx.STORE))

        results = list(hdl.connectors('pfx'))
        assert len(results) == 2


# ---------------------------------------------------------------------------
# str_ios()
# ---------------------------------------------------------------------------

class TestStrIos:
    def test_str_ios_no_inputs_no_outputs(self):
        hdl = make_hdlmodule()
        s = hdl.str_ios()
        assert '-- I/O PORTS --' in s
        assert 'Inputs: None' in s
        assert 'Outputs: None' in s

    def test_str_ios_with_inputs(self):
        hdl = make_hdlmodule()
        in_sig = hdl.gen_sig('test_in_str', 8, {'input', 'reg'})
        hdl.add_input(AHDL_VAR(in_sig, Ctx.STORE))
        s = hdl.str_ios()
        assert 'Inputs:' in s
        assert 'test_in_str' in s

    def test_str_ios_with_outputs(self):
        hdl = make_hdlmodule()
        out_sig = hdl.gen_sig('test_out_str', 8, {'output', 'net'})
        hdl.add_output(AHDL_VAR(out_sig, Ctx.STORE))
        s = hdl.str_ios()
        assert 'Outputs:' in s
        assert 'test_out_str' in s

    def test_str_ios_with_both(self):
        hdl = make_hdlmodule()
        in_sig = hdl.gen_sig('test_in_both', 8, {'input', 'reg'})
        out_sig = hdl.gen_sig('test_out_both', 8, {'output', 'net'})
        hdl.add_input(AHDL_VAR(in_sig, Ctx.STORE))
        hdl.add_output(AHDL_VAR(out_sig, Ctx.STORE))
        s = hdl.str_ios()
        assert 'test_in_both' in s
        assert 'test_out_both' in s
        assert 'Inputs: None' not in s
        assert 'Outputs: None' not in s


# ---------------------------------------------------------------------------
# __str__() comprehensive test
# ---------------------------------------------------------------------------

class TestHDLModuleStr:
    def test_str_basic_structure(self):
        hdl = make_hdlmodule()
        s = str(hdl)
        assert 'HDLModule:' in s
        assert '-- I/O PORTS --' in s
        assert '-- RESOURCE SUMMARY --' in s
        assert 'Registers:' in s
        assert 'Nets:' in s
        assert 'States:' in s

    def test_str_with_parameters(self):
        hdl = make_hdlmodule()
        param_sig = hdl.gen_sig('DATA_WIDTH', 8, {'parameter'})
        hdl.parameters[param_sig] = 32
        s = str(hdl)
        assert '-- PARAMETERS --' in s
        assert 'DATA_WIDTH' in s
        assert '32' in s

    def test_str_with_constants(self):
        hdl = make_hdlmodule()
        hdl.add_constant('CONST_A', 5)
        s = str(hdl)
        assert '-- CONSTANTS --' in s
        assert 'CONST_A' in s
        assert '5' in s

    def test_str_with_sub_modules_and_connections(self):
        hdl = make_hdlmodule()
        sub_hdl = make_hdlmodule()

        # Signals for connection
        sig1 = hdl.gen_sig('sub_port_a', 8, {'input'})
        sig2 = sub_hdl.gen_sig('inner_port', 8, {'output'})

        hdl.add_sub_module('sub_inst', sub_hdl, [(sig1, sig2)], {'W': 8})
        s = str(hdl)
        assert '-- SUB MODULES --' in s
        assert 'sub_inst' in s
        assert 'Connections:' in s
        assert 'Parameters:' in s
        assert 'W' in s

    def test_str_with_sub_modules_no_connections(self):
        hdl = make_hdlmodule()
        sub_hdl = make_hdlmodule()
        hdl.add_sub_module('sub_empty', sub_hdl, [], None)
        s = str(hdl)
        assert '-- SUB MODULES --' in s
        assert 'sub_empty' in s
        # No connections or param_map sections
        assert 'Connections:' not in s
        assert 'Parameters:' not in s

    def test_str_with_declarations(self):
        hdl = make_hdlmodule()
        assign = _make_assign(hdl, 'str_decl_dst')
        hdl.add_decl(assign)
        s = str(hdl)
        assert '-- DECLARATIONS --' in s
        assert 'str_decl_dst' in s

    def test_str_with_fsm_full(self):
        """FSM section includes state var, reset stms, outputs, STGs/states."""
        hdl = make_hdlmodule()
        hdl.add_fsm('main_fsm', hdl.scope)

        # Add output signal to FSM
        out_sig = hdl.gen_sig('fsm_out_sig', 8, {'output', 'net'})
        hdl.add_fsm_output('main_fsm', out_sig)

        # Add reset statement
        hdl.add_fsm_reset_stm('main_fsm', AHDL_NOP('rst'))

        # Add STG with 2 states
        stg = _make_stg(hdl, 'main', num_states=2)
        hdl.add_fsm_stg('main_fsm', [stg])

        s = str(hdl)
        assert '-- FINITE STATE MACHINES --' in s
        assert 'FSM: main_fsm' in s
        assert 'State Variable:' in s
        assert 'Reset Statements:' in s
        assert 'Outputs:' in s
        assert 'fsm_out_sig' in s
        assert 'State Transition Graphs:' in s
        assert 'states' in s

    def test_str_with_tasks(self):
        hdl = make_hdlmodule()
        clk_sig = hdl.gen_sig('clk', 1, {'net'})
        task = AHDL_EVENT_TASK(((clk_sig, 'posedge'),), AHDL_NOP('body'))
        hdl.add_task(task)
        s = str(hdl)
        assert '-- TASKS --' in s

    def test_str_with_edge_detectors(self):
        hdl = make_hdlmodule()
        sig = hdl.gen_sig('edge_det_sig', 1, {'net'})
        var = AHDL_VAR(sig, Ctx.LOAD)
        hdl.add_edge_detector(var, AHDL_CONST(0), AHDL_CONST(1))
        s = str(hdl)
        assert '-- EDGE DETECTORS --' in s
        assert 'edge_det_sig' in s

    def test_str_no_optional_sections_when_empty(self):
        hdl = make_hdlmodule()
        s = str(hdl)
        assert '-- PARAMETERS --' not in s
        assert '-- CONSTANTS --' not in s
        assert '-- SUB MODULES --' not in s
        assert '-- DECLARATIONS --' not in s
        assert '-- FINITE STATE MACHINES --' not in s
        assert '-- TASKS --' not in s
        assert '-- EDGE DETECTORS --' not in s

    def test_str_fsm_empty_stgs_no_stg_section(self):
        """FSM without STGs should not show STG section."""
        hdl = make_hdlmodule()
        hdl.add_fsm('empty_fsm', hdl.scope)
        s = str(hdl)
        assert 'FSM: empty_fsm' in s
        assert 'State Transition Graphs:' not in s

    def test_str_fsm_no_reset_stms(self):
        """FSM without reset_stms should not show Reset Statements section."""
        hdl = make_hdlmodule()
        hdl.add_fsm('nrst_fsm', hdl.scope)
        s = str(hdl)
        assert 'Reset Statements:' not in s

    def test_str_fsm_no_outputs(self):
        """FSM without outputs should not show 'Outputs:\n' (only 'Outputs: None' from I/O)."""
        hdl = make_hdlmodule()
        hdl.add_fsm('nout_fsm', hdl.scope)
        s = str(hdl)
        assert 'FSM: nout_fsm' in s
        # No FSM outputs added; the only 'Outputs:' present is from str_ios()
        # which always renders 'Outputs: None' or 'Outputs:\n'.
        # The FSM-specific outputs block starts with '    Outputs:\n', check it's absent.
        assert '    Outputs:\n' not in s


# ---------------------------------------------------------------------------
# clone()
# ---------------------------------------------------------------------------

class TestHDLModuleClone:
    def test_clone_basic(self):
        hdl = make_hdlmodule()
        hdl.gen_sig('clone_reg', 8, {'reg'})
        hdl.gen_sig('clone_net', 4, {'net'})

        cloned = hdl.clone()
        assert cloned is not hdl
        assert cloned.name == hdl.name
        assert 'clone_reg' in cloned.signals
        assert 'clone_net' in cloned.signals

    def test_clone_inputs_outputs_copied(self):
        hdl = make_hdlmodule()
        in_sig = hdl.gen_sig('test_clone_in', 8, {'input', 'reg'})
        out_sig = hdl.gen_sig('test_clone_out', 8, {'output', 'net'})
        hdl.add_input(AHDL_VAR(in_sig, Ctx.STORE))
        hdl.add_output(AHDL_VAR(out_sig, Ctx.STORE))

        cloned = hdl.clone()
        assert len(cloned.inputs()) == 1
        assert len(cloned.outputs()) == 1

    def test_clone_fsms_copied(self):
        hdl = make_hdlmodule()
        hdl.add_fsm('clone_fsm', hdl.scope)
        cloned = hdl.clone()
        assert 'clone_fsm' in cloned.fsms

    def test_clone_functions_copied(self):
        hdl = make_hdlmodule()
        out_sig = hdl.gen_sig('clone_func_out', 8, {'net'})
        out_var = AHDL_VAR(out_sig, Ctx.STORE)
        func = AHDL_FUNCTION(out_var, (), ())
        hdl.add_function(func)
        cloned = hdl.clone()
        assert len(cloned.functions) == 1

    def test_clone_constants_copied(self):
        hdl = make_hdlmodule()
        hdl.add_constant('CLONE_CONST', 99)
        cloned = hdl.clone()
        vals = list(cloned.constants.values())
        assert 99 in vals

    def test_clone_edge_detectors_copied(self):
        hdl = make_hdlmodule()
        sig = hdl.gen_sig('clone_edge', 1, {'net'})
        var = AHDL_VAR(sig, Ctx.LOAD)
        hdl.add_edge_detector(var, AHDL_CONST(0), AHDL_CONST(1))
        cloned = hdl.clone()
        assert len(cloned.edge_detectors) == 1
