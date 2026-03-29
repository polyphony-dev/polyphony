"""Tests for HDLModuleBuilder and subclasses in hdlgen.py."""
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_MOVE, AHDL_NOP, AHDL_VAR, Ctx,
)
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ahdl.hdlmodule import HDLModule, FSM
from polyphony.compiler.ahdl.hdlgen import (
    HDLModuleBuilder, HDLFunctionModuleBuilder,
    HDLTestbenchBuilder, HDLTopModuleBuilder,
)
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


_SRC_FUNC = '''
scope test
tags function function_module returnable
return int32
'''

_SRC_FUNC_WITH_PARAM = '''
scope testp
tags function function_module returnable
param a: int32
return int32
'''

_SRC_TB = '''
scope testtb
tags testbench
'''

_SRC_MOD = '''
scope testmod
tags class module
'''

_SRC_MOD_INST = '''
scope testmod
tags class module instantiated
'''


def build_scope(src):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule(scope):
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def _make_fsm(hdl, name='main'):
    state_sig = hdl.gen_sig(f'{name}_state', 4, {'reg'})
    fsm = FSM(name, hdl.scope, state_sig)
    hdl.fsms[name] = fsm
    return fsm


def _make_fsm_with_stg(hdl, codes=(), fsm_name='main'):
    fsm = _make_fsm(hdl, fsm_name)
    stg = STG(fsm_name, None, hdl)
    block = AHDL_BLOCK('S0', codes)
    state = stg.new_state('S0', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    return fsm, stg


def _make_sig(hdl, name, tags):
    return Signal(hdl, name, 8, tags, None)


# ============================================================
# HDLModuleBuilder.create() — lines 17-25
# ============================================================

def test_create_returns_function_module_builder():
    """create() with function_module scope returns HDLFunctionModuleBuilder."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    builder = HDLModuleBuilder.create(hdl)
    assert isinstance(builder, HDLFunctionModuleBuilder)


def test_create_returns_testbench_builder():
    """create() with testbench scope returns HDLTestbenchBuilder."""
    scope = build_scope(_SRC_TB)
    hdl = make_hdlmodule(scope)
    builder = HDLModuleBuilder.create(hdl)
    assert isinstance(builder, HDLTestbenchBuilder)


def test_create_returns_top_module_builder():
    """create() with module scope returns HDLTopModuleBuilder."""
    scope = build_scope(_SRC_MOD)
    hdl = make_hdlmodule(scope)
    builder = HDLModuleBuilder.create(hdl)
    assert isinstance(builder, HDLTopModuleBuilder)


# ============================================================
# HDLModuleBuilder.process() — lines 27-30
# ============================================================

def test_process_sets_hdlmodule():
    """process() sets self.hdlmodule and calls _build_module (base is no-op)."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    builder = HDLModuleBuilder()
    builder.process(hdl)
    assert builder.hdlmodule is hdl


# ============================================================
# HDLModuleBuilder._collect_moves() — lines 101-106
# ============================================================

def test_collect_moves_returns_moves():
    """_collect_moves() returns all AHDL_MOVE instances from FSM states."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    mv = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(1))
    fsm, _ = _make_fsm_with_stg(hdl, codes=(mv, AHDL_NOP('nop')))

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    moves = builder._collect_moves(fsm)
    assert len(moves) == 1
    assert moves[0] is mv


def test_collect_moves_empty_returns_empty_list():
    """_collect_moves() returns empty list when no AHDL_MOVE in states."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    fsm, _ = _make_fsm_with_stg(hdl, codes=(AHDL_NOP('nop'),))

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    moves = builder._collect_moves(fsm)
    assert moves == []


def test_collect_moves_multiple_stgs():
    """_collect_moves() collects from all STGs."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    reg_sig = hdl.gen_sig('r', 8, {'reg'})
    mv1 = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(1))
    mv2 = AHDL_MOVE(AHDL_VAR(reg_sig, Ctx.STORE), AHDL_CONST(2))

    state_sig = hdl.gen_sig('state', 4, {'reg'})
    fsm = FSM('main', scope, state_sig)
    hdl.fsms['main'] = fsm

    for i, mv in enumerate([mv1, mv2]):
        stg = STG(f'stg{i}', None, hdl)
        block = AHDL_BLOCK(f'S{i}', (mv,))
        state = stg.new_state(f'S{i}', block, 0)
        stg.set_states([state])
        fsm.stgs.append(stg)

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    moves = builder._collect_moves(fsm)
    assert len(moves) == 2


# ============================================================
# HDLModuleBuilder._add_reset_stms() — lines 108-119
# ============================================================

def test_add_reset_stms_adds_reg_signal():
    """_add_reset_stms() adds AHDL_MOVE(sig, CONST(0)) for reg signal."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    fsm = _make_fsm(hdl)

    sig = _make_sig(hdl, 'r', {'reg'})
    defs = {(sig,)}

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_reset_stms(fsm, defs, set(), set())

    assert len(fsm.reset_stms) == 1
    stm = fsm.reset_stms[0]
    assert isinstance(stm, AHDL_MOVE)
    assert isinstance(stm.src, AHDL_CONST)
    assert stm.src.value == 0


def test_add_reset_stms_initializable_uses_init_value():
    """_add_reset_stms() uses init_value when signal is initializable."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    fsm = _make_fsm(hdl)

    sig = _make_sig(hdl, 'r_init', {'reg', 'initializable'})
    sig.init_value = 7
    defs = {(sig,)}

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_reset_stms(fsm, defs, set(), set())

    assert len(fsm.reset_stms) == 1
    stm = fsm.reset_stms[0]
    assert stm.src.value == 7


def test_add_reset_stms_dut_signal_skipped():
    """_add_reset_stms() skips signals with 'dut' tag."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    fsm = _make_fsm(hdl)

    sig = _make_sig(hdl, 'r_dut', {'reg', 'dut'})
    defs = {(sig,)}

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_reset_stms(fsm, defs, set(), set())

    assert len(fsm.reset_stms) == 0


def test_add_reset_stms_non_reg_skipped():
    """_add_reset_stms() skips signals that are not reg."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    fsm = _make_fsm(hdl)

    sig = _make_sig(hdl, 'n', {'net'})
    defs = {(sig,)}

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_reset_stms(fsm, defs, set(), set())

    assert len(fsm.reset_stms) == 0


def test_add_reset_stms_outputs_included():
    """_add_reset_stms() processes defs | outputs together."""
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    fsm = _make_fsm(hdl)

    sig_d = _make_sig(hdl, 'rd', {'reg'})
    sig_o = _make_sig(hdl, 'ro', {'reg'})
    defs = {(sig_d,)}
    outputs = {(sig_o,)}

    builder = HDLModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_reset_stms(fsm, defs, set(), outputs)

    assert len(fsm.reset_stms) == 2


# ============================================================
# HDLTopModuleBuilder._build_module() early return — lines 204-208
# ============================================================

def test_top_module_not_instantiated_returns_early():
    """_build_module() returns early when scope is not instantiated."""
    scope = build_scope(_SRC_MOD)
    assert scope.is_module()
    assert not scope.is_instantiated()
    hdl = make_hdlmodule(scope)

    builder = HDLTopModuleBuilder()
    builder.hdlmodule = hdl
    builder._collector = type('C', (), {'process': lambda self, x: None})()
    # Should return without error — early return on line 208
    builder._build_module()
    # No FSMs or params processed
    assert hdl.parameters == {}


# ============================================================
# HDLFunctionModuleBuilder._build_module() — lines 124-134
# ============================================================

def _make_function_module_hdl():
    scope = build_scope(_SRC_FUNC)
    hdl = make_hdlmodule(scope)
    # Pre-create output signal that _add_output expects
    hdl.gen_sig('test_out_0', 32, {'output', 'reg'})
    # FSM must be keyed by hdlmodule.name
    state_sig = hdl.gen_sig('test_state', 4, {'reg'})
    fsm = FSM('test', scope, state_sig)
    from polyphony.compiler.ahdl.stg import STG
    stg = STG('test', None, hdl)
    block = AHDL_BLOCK('INIT', ())
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['test'] = fsm
    return hdl, fsm, scope


def test_function_module_builder_process():
    """HDLFunctionModuleBuilder.process() adds ready/accept inputs and valid output."""
    hdl, fsm, scope = _make_function_module_hdl()
    from polyphony.compiler.ahdl.hdlgen import HDLFunctionModuleBuilder
    HDLFunctionModuleBuilder().process(hdl)

    input_sigs = list(hdl.get_signals({'input'}))
    output_sigs = list(hdl.get_signals({'output'}))
    input_names = [s.name for s in input_sigs]
    output_names = [s.name for s in output_sigs]
    assert 'test_ready' in input_names
    assert 'test_accept' in input_names
    assert 'test_out_0' in output_names
    assert 'test_valid' in output_names


# ============================================================
# HDLFunctionModuleBuilder._add_input() — lines 137-152
# ============================================================

def test_add_input_no_params_creates_ready_accept():
    """_add_input() with no params still adds ready and accept signals."""
    hdl, _, scope = _make_function_module_hdl()
    builder = HDLFunctionModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_input(scope)

    input_names = [s.name for s in hdl.get_signals({'input'})]
    assert 'test_ready' in input_names
    assert 'test_accept' in input_names


def test_add_input_with_int_param():
    """_add_input() with int param creates input signal for the param."""
    scope = build_scope(_SRC_FUNC_WITH_PARAM)
    hdl = make_hdlmodule(scope)
    hdl.gen_sig('testp_out_0', 32, {'output', 'reg'})

    # Pre-create the param signal keyed by symbol (STGBuilder normally does this)
    param_syms = list(scope.param_symbols())
    assert len(param_syms) == 1
    sym = param_syms[0]
    hdl.gen_sig(sym.hdl_name(), 32, {'input', 'reg'}, sym)

    builder = HDLFunctionModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_input(scope)

    input_names = [s.name for s in hdl.get_signals({'input'})]
    assert sym.hdl_name() in input_names
    assert 'testp_ready' in input_names
    assert 'testp_accept' in input_names


# ============================================================
# HDLFunctionModuleBuilder._add_output() — lines 155-164
# ============================================================

def test_add_output_scalar_creates_out_and_valid():
    """_add_output() with scalar return type adds out_0 and valid signals."""
    hdl, _, scope = _make_function_module_hdl()
    builder = HDLFunctionModuleBuilder()
    builder.hdlmodule = hdl
    builder._add_output(scope)

    output_names = [s.name for s in hdl.get_signals({'output'})]
    assert 'test_out_0' in output_names
    assert 'test_valid' in output_names


# ============================================================
# HDLTestbenchBuilder._build_module() — lines 169-175
# ============================================================

def test_testbench_builder_process():
    """HDLTestbenchBuilder.process() completes without error on minimal testbench."""
    scope = build_scope(_SRC_TB)
    hdl = make_hdlmodule(scope)
    state_sig = hdl.gen_sig('testtb_state', 4, {'reg'})
    fsm = FSM('testtb', scope, state_sig)
    from polyphony.compiler.ahdl.stg import STG
    stg = STG('testtb', None, hdl)
    block = AHDL_BLOCK('INIT', ())
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['testtb'] = fsm

    HDLTestbenchBuilder().process(hdl)
    # Completed without error
    assert 'testtb' in hdl.fsms


# ============================================================
# HDLTopModuleBuilder._process_io() — lines 184-194
# ============================================================

def test_process_io_adds_input_output():
    """_process_io() adds input/output for single_port signals."""
    scope = build_scope(_SRC_MOD_INST)
    hdl = make_hdlmodule(scope)
    hdl.gen_sig('p_in', 8, {'single_port', 'input', 'reg'})
    hdl.gen_sig('p_out', 8, {'single_port', 'output', 'net'})

    from polyphony.compiler.ahdl.transformers.varcollector import AHDLVarCollector
    builder = HDLTopModuleBuilder()
    builder.hdlmodule = hdl
    builder._collector = AHDLVarCollector()
    builder._process_io(hdl)

    input_names = [s.name for s in hdl.get_signals({'input'})]
    output_names = [s.name for s in hdl.get_signals({'output'})]
    assert 'p_in' in input_names
    assert 'p_out' in output_names


# ============================================================
# HDLTopModuleBuilder._build_module() instantiated — lines 209-229
# ============================================================

def test_top_module_builder_process_instantiated_no_fsms():
    """HDLTopModuleBuilder.process() on instantiated module with no FSMs."""
    scope = build_scope(_SRC_MOD_INST)
    hdl = make_hdlmodule(scope)

    HDLTopModuleBuilder().process(hdl)
    # No module_params, no FSMs — should complete without error
    assert hdl.parameters == {}


def test_top_module_builder_process_with_fsm():
    """HDLTopModuleBuilder.process() processes FSMs via _process_fsm()."""
    scope = build_scope(_SRC_MOD_INST)
    hdl = make_hdlmodule(scope)

    # Add a non-ctor FSM
    state_sig = hdl.gen_sig('testmod_state', 4, {'reg'})
    fsm = FSM('testmod', scope, state_sig)
    from polyphony.compiler.ahdl.stg import STG
    stg = STG('testmod', None, hdl)
    block = AHDL_BLOCK('INIT', ())
    state = stg.new_state('INIT', block, 0)
    stg.set_states([state])
    fsm.stgs.append(stg)
    hdl.fsms['testmod'] = fsm

    HDLTopModuleBuilder().process(hdl)
    # FSM still exists, no error
    assert 'testmod' in hdl.fsms
