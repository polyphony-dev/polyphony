import ctypes
import os
import subprocess
import sys
import tempfile
import types

import pytest


def test_cmodelevaluator_eval_simple():
    """Compile a trivial C module, load it, verify eval cycle."""
    from polyphony.simulator import CModelEvaluator

    c_source = '''
#include <stdint.h>
static inline int64_t mask(int64_t v, int w) {
    if (w >= 64) return v;
    return v & ((1LL << w) - 1);
}
#define S_clk      0
#define S_a        1
#define S_result   2
#define S_result_next 3
#define S_NUM_SIGNALS 4

void module_eval_tasks(int64_t* s) {
    if (s[S_clk] == 1) {
        s[S_result_next] = mask(s[S_a] + 1, 32);
    }
}

void module_update_regs(int64_t* s) {
    s[S_result] = s[S_result_next];
}

int module_eval_decls(int64_t* s) {
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, 'test.c')
        so_path = os.path.join(tmpdir, 'test.so')
        with open(c_path, 'w') as f:
            f.write(c_source)
        result = subprocess.run(
            ['gcc', '-O2', '-shared', '-fPIC', '-o', so_path, c_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip(f'gcc not available: {result.stderr}')

        port_map = {'clk': 0, 'a': 1, 'result': 2}
        ev = CModelEvaluator(so_path, 4, port_map)

        ev.write_port('a', 10)
        ev.write_port('clk', 1)
        ev.eval()
        assert ev.read_port('result') == 11


def test_cmodelevaluator_zero_copy():
    """Verify direct buffer access."""
    from polyphony.simulator import CModelEvaluator

    c_source = '''
#include <stdint.h>
void module_eval_tasks(int64_t* s) {}
void module_update_regs(int64_t* s) {}
int module_eval_decls(int64_t* s) { return 0; }
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, 'test.c')
        so_path = os.path.join(tmpdir, 'test.so')
        with open(c_path, 'w') as f:
            f.write(c_source)
        result = subprocess.run(
            ['gcc', '-O2', '-shared', '-fPIC', '-o', so_path, c_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip('gcc not available')

        ev = CModelEvaluator(so_path, 4, {'x': 0})
        ev.write_port('x', 42)
        assert ev._buf[0] == 42
        assert ev.read_port('x') == 42


def test_cmodelevaluator_get_signal():
    """Verify get_signal for internal signals."""
    from polyphony.simulator import CModelEvaluator

    c_source = '''
#include <stdint.h>
void module_eval_tasks(int64_t* s) {}
void module_update_regs(int64_t* s) {}
int module_eval_decls(int64_t* s) { return 0; }
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, 'test.c')
        so_path = os.path.join(tmpdir, 'test.so')
        with open(c_path, 'w') as f:
            f.write(c_source)
        result = subprocess.run(
            ['gcc', '-O2', '-shared', '-fPIC', '-o', so_path, c_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip('gcc not available')

        sig_map = {'x': 0, 'y': 1, 'internal': 2}
        port_map = {'x': 0, 'y': 1}
        ev = CModelEvaluator(so_path, 4, port_map, sig_map)
        ev._buf[2] = 99
        assert ev.get_signal('internal') == 99


def test_csimulator_model_builder_compile():
    """CSimulatorModelBuilder compiles C source to .so."""
    from polyphony.simulator import CSimulatorModelBuilder, CModelEvaluator
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from test_csimgen import _make_simple_hdlscope

    scope = _make_simple_hdlscope()

    with tempfile.TemporaryDirectory() as tmpdir:
        builder = CSimulatorModelBuilder()
        try:
            evaluator = builder.build(scope, output_dir=tmpdir)
        except (RuntimeError, FileNotFoundError) as e:
            pytest.skip(f'gcc not available: {e}')

        assert isinstance(evaluator, CModelEvaluator)
        # Check cache files
        files = os.listdir(tmpdir)
        assert any(f.endswith('.so') for f in files)
        assert any(f.endswith('.hash') for f in files)


def test_csimulator_model_builder_cache():
    """Second build uses cache (no recompile)."""
    from polyphony.simulator import CSimulatorModelBuilder, CModelEvaluator
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from test_csimgen import _make_simple_hdlscope

    scope = _make_simple_hdlscope()

    with tempfile.TemporaryDirectory() as tmpdir:
        builder = CSimulatorModelBuilder()
        try:
            ev1 = builder.build(scope, output_dir=tmpdir)
        except (RuntimeError, FileNotFoundError):
            pytest.skip('gcc not available')

        # Get .so modification time
        so_files = [f for f in os.listdir(tmpdir) if f.endswith('.so')]
        so_mtime = os.path.getmtime(os.path.join(tmpdir, so_files[0]))

        # Build again -- should use cache
        import time; time.sleep(0.01)
        ev2 = builder.build(scope, output_dir=tmpdir)
        so_mtime2 = os.path.getmtime(os.path.join(tmpdir, so_files[0]))

        assert isinstance(ev2, CModelEvaluator)
        assert so_mtime == so_mtime2  # .so was NOT recompiled


def test_simulator_classes_exist():
    """Verify CModelEvaluator and CSimulatorModelBuilder are importable."""
    from polyphony.simulator import CModelEvaluator, CSimulatorModelBuilder, Simulator
    assert CModelEvaluator is not None
    assert CSimulatorModelBuilder is not None
    assert Simulator is not None


# ---------------------------------------------------------------------------
# End-to-end integration test: compile expr01.py -> C -> .so -> simulate
# ---------------------------------------------------------------------------

def _compile_test_case(casefile_path):
    """Run the full polyphony compiler pipeline on a test file.

    Returns the list of compiled scopes, or raises on failure.
    The caller must call env.destroy() when done.
    """
    from polyphony.compiler.__main__ import (
        setup, compile_plan, output_plan, output_hdl,
        compile as compile_polyphony,
    )
    from polyphony.compiler.common.common import read_source
    from polyphony.compiler.common.env import env

    casename = os.path.splitext(os.path.basename(casefile_path))[0]

    compiler_options = types.SimpleNamespace()
    compiler_options.output_name = casename
    compiler_options.output_prefix = ''
    compiler_options.output_dir = tempfile.mkdtemp(prefix='csim_e2e_')
    compiler_options.verbose_level = 0
    compiler_options.quiet_level = 3
    compiler_options.targets = []
    compiler_options.config = None
    compiler_options.debug_mode = False
    compiler_options.hdl_debug_mode = False
    compiler_options.verilog_dump = False
    compiler_options.verilog_monitor = False
    compiler_options.watch_signals = ''

    setup(casefile_path, compiler_options)

    source_text = read_source(casefile_path)
    plan = compile_plan()
    scopes = compile_polyphony(plan, source_text, casefile_path)
    output_hdl(output_plan(), scopes, compiler_options, stage_offset=len(plan))

    return scopes, compiler_options.output_dir


def _find_expr01_test():
    """Locate tests/expr/expr01.py relative to the project root."""
    # Walk up from this test file to find the project root
    here = os.path.dirname(os.path.abspath(__file__))
    # pytests/compiler/target/csim -> project root (4 levels up)
    root = os.path.normpath(os.path.join(here, '..', '..', '..', '..'))
    candidate = os.path.join(root, 'tests', 'expr', 'expr01.py')
    if os.path.isfile(candidate):
        return candidate
    pytest.skip(f'tests/expr/expr01.py not found (looked in {candidate})')


def test_e2e_transpile_expr01():
    """End-to-end: compile expr01.py through full pipeline, transpile to C,
    compile to .so, run CModelEvaluator, compare against Python ModelEvaluator.

    This is the core integration test for the csim transpiler.
    """
    import shutil

    # Check gcc availability up-front
    result = subprocess.run(['gcc', '--version'], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip('gcc not available')

    casefile = _find_expr01_test()

    from polyphony.compiler.common.env import env
    from polyphony.simulator import (
        SimulationModelBuilder, ModelEvaluator,
        CSimulatorModelBuilder, CModelEvaluator,
        Simulator, Reg, Net, Port,
    )

    scopes = None
    output_dir = None
    try:
        scopes, output_dir = _compile_test_case(casefile)

        # Find the HDLModule for expr01 (the function under test).
        # After compilation, env.testbenches lists testbench scopes.
        # The sub_modules of the testbench's HDLModule contain the DUT.
        assert len(env.testbenches) > 0, 'No testbenches found after compilation'

        testbench = env.testbenches[0]
        test_hdlmodule = env.hdlscope(testbench)

        # Collect the DUT HDLModules
        dut_hdlmodules = {}
        for _, sub_hdlmodule, _, _ in test_hdlmodule.sub_modules.values():
            if sub_hdlmodule.name not in dut_hdlmodules:
                dut_hdlmodules[sub_hdlmodule.name] = sub_hdlmodule

        assert len(dut_hdlmodules) > 0, 'No sub-modules found in testbench'

        # Pick the first (and likely only) DUT module
        dut_name = list(dut_hdlmodules.keys())[0]
        hdlmodule = dut_hdlmodules[dut_name]

        # ---- Step 1: Transpile to C ----
        from polyphony.compiler.target.csim.csimgen import AHDLToCTranspiler

        transpiler = AHDLToCTranspiler()
        transpile_error = None
        try:
            c_source, sig_map, port_map, sig_count = transpiler.generate(hdlmodule)
        except NotImplementedError as e:
            transpile_error = e
            pytest.skip(f'Transpiler hit unsupported AHDL node: {e}')
        except Exception as e:
            transpile_error = e
            pytest.fail(f'Transpiler failed unexpectedly: {e}')

        # Verify we got non-empty output
        assert len(c_source) > 0, 'Empty C source generated'
        assert sig_count > 0, 'No signals assigned'
        assert 'module_eval_tasks' in c_source
        assert 'module_update_regs' in c_source
        assert 'module_eval_decls' in c_source

        # ---- Step 2: Build the .so via CSimulatorModelBuilder ----
        csim_dir = os.path.join(output_dir, 'csim')
        builder = CSimulatorModelBuilder()
        c_evaluator = builder.build(hdlmodule, output_dir=csim_dir)
        assert isinstance(c_evaluator, CModelEvaluator)

        # ---- Step 3: Build Python ModelEvaluator for comparison ----
        # We need a dummy main_py_module for SimulationModelBuilder
        source_text = open(casefile).read()
        main_py_module = types.ModuleType('__main__')
        code_obj = compile(source_text, casefile, 'exec')
        exec(code_obj, main_py_module.__dict__)

        py_model = SimulationModelBuilder().build_model(hdlmodule, main_py_module, is_top=True)
        py_core = getattr(py_model, '__model')
        py_evaluator = ModelEvaluator(py_core)

        # ---- Step 4: Compare eval results ----
        # expr01 is a function module with handshake signals.
        # The port_map from transpiler tells us which ports exist.
        # We run several clock cycles and compare the C and Python evaluators.

        # Reset phase: rst=1 for one cycle
        if 'rst' in port_map:
            c_evaluator.write_port('rst', 1)
        if hasattr(py_core, 'rst'):
            py_core.rst.val = 1
        if 'clk' in port_map:
            c_evaluator.write_port('clk', 1)
        if hasattr(py_core, 'clk'):
            py_core.clk.val = 1

        c_evaluator.eval()
        py_evaluator.eval()

        if 'rst' in port_map:
            c_evaluator.write_port('rst', 0)
        if hasattr(py_core, 'rst'):
            py_core.rst.val = 0

        # Run a few clock cycles with specific input to exercise the function.
        # For a function module, we need to drive the handshake:
        #   - set <func>_ready = 1, <func>_in_a = value
        #   - clock until <func>_valid = 1
        #   - read <func>_out_0

        # Discover handshake signals from port_map
        ready_port = None
        valid_port = None
        accept_port = None
        in_a_port = None
        out_port = None
        for name in port_map:
            if name.endswith('_ready'):
                ready_port = name
            elif name.endswith('_valid'):
                valid_port = name
            elif name.endswith('_accept'):
                accept_port = name
            elif name.endswith('_in_a'):
                in_a_port = name
            elif name.endswith('_out_0'):
                out_port = name

        if not all([ready_port, valid_port, in_a_port, out_port]):
            # Not a standard function module -- just verify the transpile succeeded
            # and run a few generic clock cycles
            for _ in range(5):
                c_evaluator.write_port('clk', 1)
                c_evaluator.eval()
                c_evaluator.write_port('clk', 0)
            return

        # Test with input values [0, 1, 2] -- expr01 returns a+1+1 = a+2
        test_inputs = [0, 1, 2]
        expected_outputs = [2, 3, 4]

        for input_val, expected in zip(test_inputs, expected_outputs):
            # Drive ready and input
            c_evaluator.write_port(ready_port, 1)
            c_evaluator.write_port(in_a_port, input_val)

            # Also drive Python model
            if hasattr(py_core, ready_port):
                attr = getattr(py_core, ready_port)
                if isinstance(attr, Port):
                    attr.value.set(1)
                elif isinstance(attr, (Reg, Net)):
                    attr.set(1)
            if hasattr(py_core, in_a_port):
                attr = getattr(py_core, in_a_port)
                if isinstance(attr, Port):
                    attr.value.set(input_val)
                elif isinstance(attr, (Reg, Net)):
                    attr.set(input_val)

            # Clock until valid or timeout
            max_cycles = 50
            c_valid = False
            py_valid = False
            for cycle in range(max_cycles):
                c_evaluator.write_port('clk', 1)
                c_evaluator.eval()
                py_core.clk.val = 1
                py_evaluator.eval()

                c_evaluator.write_port('clk', 0)
                py_core.clk.val = 0

                if valid_port in port_map:
                    c_valid = c_evaluator.read_port(valid_port) == 1
                py_valid_attr = getattr(py_core, valid_port, None)
                if py_valid_attr is not None:
                    if isinstance(py_valid_attr, Port):
                        py_valid = py_valid_attr.value.get() == 1
                    elif isinstance(py_valid_attr, (Reg, Net)):
                        py_valid = py_valid_attr.get() == 1

                if c_valid:
                    break

            assert c_valid, (
                f'C evaluator did not produce valid=1 within {max_cycles} cycles '
                f'for input={input_val}'
            )

            # Read output
            c_result = c_evaluator.read_port(out_port)

            # Read Python output for comparison
            py_result = None
            py_out_attr = getattr(py_core, out_port, None)
            if py_out_attr is not None:
                if isinstance(py_out_attr, Port):
                    py_result = py_out_attr.value.get()
                elif isinstance(py_out_attr, (Reg, Net)):
                    py_result = py_out_attr.get()

            # Verify C result matches expected
            assert c_result == expected, (
                f'C evaluator: input={input_val}, got={c_result}, expected={expected}'
            )

            # Verify C and Python agree
            if py_valid and py_result is not None:
                assert c_result == py_result, (
                    f'C vs Python mismatch: input={input_val}, '
                    f'c_result={c_result}, py_result={py_result}'
                )

            # Complete handshake: accept
            if accept_port:
                c_evaluator.write_port(accept_port, 1)
                if hasattr(py_core, accept_port):
                    attr = getattr(py_core, accept_port)
                    if isinstance(attr, Port):
                        attr.value.set(1)
                    elif isinstance(attr, (Reg, Net)):
                        attr.set(1)

            c_evaluator.write_port('clk', 1)
            c_evaluator.eval()
            py_core.clk.val = 1
            py_evaluator.eval()
            c_evaluator.write_port('clk', 0)
            py_core.clk.val = 0

            # Deassert handshake
            c_evaluator.write_port(ready_port, 0)
            if accept_port:
                c_evaluator.write_port(accept_port, 0)
            if hasattr(py_core, ready_port):
                attr = getattr(py_core, ready_port)
                if isinstance(attr, Port):
                    attr.value.set(0)
                elif isinstance(attr, (Reg, Net)):
                    attr.set(0)
            if accept_port and hasattr(py_core, accept_port):
                attr = getattr(py_core, accept_port)
                if isinstance(attr, Port):
                    attr.value.set(0)
                elif isinstance(attr, (Reg, Net)):
                    attr.set(0)

            c_evaluator.write_port('clk', 1)
            c_evaluator.eval()
            py_core.clk.val = 1
            py_evaluator.eval()
            c_evaluator.write_port('clk', 0)
            py_core.clk.val = 0

    finally:
        env.destroy()
        if output_dir and os.path.isdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)


def test_cbuffersignal_val_property():
    """CBufferSignal.val reads/writes ctypes buffer directly."""
    import ctypes
    from polyphony.simulator import CBufferSignal

    buf = (ctypes.c_int64 * 4)()
    sig = CBufferSignal(buf, idx=1, width=32, is_signed=False)
    assert sig.val == 0
    sig.val = 42
    assert sig.val == 42
    assert buf[1] == 42
    # Direct buffer write is visible through .val
    buf[1] = 99
    assert sig.val == 99


def test_cbuffersignal_set_get():
    """CBufferSignal.set() applies mask, .get() returns raw value."""
    import ctypes
    from polyphony.simulator import CBufferSignal

    buf = (ctypes.c_int64 * 4)()
    sig = CBufferSignal(buf, idx=0, width=8, is_signed=False)
    sig.set(0x1FF)  # 9 bits -> masked to 8 bits
    assert sig.get() == 0xFF
    assert buf[0] == 0xFF


def test_cbuffersignal_toInteger():
    """CBufferSignal.toInteger() returns Integer with correct width/sign."""
    import ctypes
    from polyphony.simulator import CBufferSignal, Integer

    buf = (ctypes.c_int64 * 4)()
    sig = CBufferSignal(buf, idx=0, width=16, is_signed=True)
    buf[0] = 42
    result = sig.toInteger()
    assert isinstance(result, Integer)
    assert result.val == 42
    assert result.width == 16
    assert result.sign is True


def test_bind_ports_replaces_clk_rst():
    """After bind_ports_to_buffer, model.clk/rst are CBufferSignal instances
    that write directly to the C buffer."""
    import ctypes
    import types
    from polyphony.simulator import CBufferSignal, Reg, CModelEvaluator

    # Minimal mock model with clk/rst as Reg
    model = types.SimpleNamespace()
    clk_sig = types.SimpleNamespace(name='clk', width=1, tags=set())
    clk_sig.is_int = lambda: False
    rst_sig = types.SimpleNamespace(name='rst', width=1, tags=set())
    rst_sig.is_int = lambda: False
    model.clk = Reg(0, 1, clk_sig)
    model.rst = Reg(0, 1, rst_sig)

    # Minimal CModelEvaluator with buffer
    buf = (ctypes.c_int64 * 4)()
    port_map = {'clk': 0, 'rst': 1, 'a': 2, 'result': 3}

    CModelEvaluator.bind_ports_to_buffer(model, buf, port_map)

    assert isinstance(model.clk, CBufferSignal)
    assert isinstance(model.rst, CBufferSignal)

    model.clk.val = 1
    assert buf[0] == 1
    model.rst.val = 1
    assert buf[1] == 1


def test_bind_ports_replaces_io_ports():
    """After bind_ports_to_buffer, Port.value is CBufferSignal."""
    import ctypes
    import types
    from polyphony.simulator import CBufferSignal, Port, Reg, Net, CModelEvaluator

    model = types.SimpleNamespace()
    clk_sig = types.SimpleNamespace(name='clk', width=1, tags=set())
    clk_sig.is_int = lambda: False
    rst_sig = types.SimpleNamespace(name='rst', width=1, tags=set())
    rst_sig.is_int = lambda: False
    model.clk = Reg(0, 1, clk_sig)
    model.rst = Reg(0, 1, rst_sig)

    # Input port 'a'
    a_sig = types.SimpleNamespace(name='a', width=32, tags=set())
    a_sig.is_int = lambda: False
    a_sig.is_input = lambda: True
    a_sig.is_output = lambda: False
    a_port = Port(None, None, None)
    a_port._set_value(Reg(0, 32, a_sig))
    model.a = a_port

    # Output port 'result'
    r_sig = types.SimpleNamespace(name='result', width=32, tags=set())
    r_sig.is_int = lambda: False
    r_sig.is_input = lambda: False
    r_sig.is_output = lambda: True
    r_port = Port(None, None, None)
    r_port._set_value(Reg(0, 32, r_sig))
    model.result = r_port

    buf = (ctypes.c_int64 * 4)()
    port_map = {'clk': 0, 'rst': 1, 'a': 2, 'result': 3}

    CModelEvaluator.bind_ports_to_buffer(model, buf, port_map)

    # wr() on input port is deferred — not yet in buffer
    model.a.wr(42)
    assert buf[2] == 0, "deferred input port should not write to buffer on wr()"
    # flush makes it visible
    model.a.value.flush_pending()
    assert buf[2] == 42

    # rd() should read from C buffer
    buf[3] = 99
    assert model.result.rd() == 99


def test_load_initial_values():
    """CSimulatorModelBuilder._load_initial_values writes Reg init values to C buffer."""
    import ctypes
    import os
    import subprocess
    import tempfile
    from polyphony.simulator import CModelEvaluator, CSimulatorModelBuilder

    c_source = '''
#include <stdint.h>
void module_eval_tasks(int64_t* s) {}
void module_update_regs(int64_t* s) {}
int module_eval_decls(int64_t* s) { return 0; }
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, 'test.c')
        so_path = os.path.join(tmpdir, 'test.so')
        with open(c_path, 'w') as f:
            f.write(c_source)
        result = subprocess.run(
            ['gcc', '-O2', '-shared', '-fPIC', '-o', so_path, c_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip('gcc not available')

        sig_map = {'counter': 0, 'counter_next': 1}
        ev = CModelEvaluator(so_path, 2, {}, sig_map)

        # Mock HDLScope with one Reg signal that has init_value
        import types
        mock_sig = types.SimpleNamespace(
            name='counter', width=32, init_value=42,
        )
        mock_sig.is_reg = lambda: True
        mock_sig.is_regarray = lambda: False
        mock_sig.is_initializable = lambda: True
        mock_sig.is_int = lambda: False

        mock_scope = types.SimpleNamespace(subscopes={})
        mock_scope.get_signals = lambda include_tags=None: (
            [mock_sig] if 'reg' in include_tags else []
        )

        # Mock transpiler with sig_map
        mock_transpiler = types.SimpleNamespace(_sig_map=sig_map)

        builder = CSimulatorModelBuilder()
        builder._load_initial_values(ev, mock_scope, mock_transpiler)

        assert ev._buf[0] == 42  # counter initial value loaded


def test_e2e_port_sync_via_cbuffersignal():
    """Full cycle: model.clk.val=1 → eval → port.rd() returns C-computed result.
    Simulates what _period() + testbench port access does."""
    import ctypes
    import os
    import subprocess
    import tempfile
    import types
    from polyphony.simulator import (
        CBufferSignal, CModelEvaluator, Port, Reg, Net,
    )

    # C module: result = a + b (on rising clk edge)
    c_source = '''
#include <stdint.h>
static inline int64_t mask(int64_t v, int w) {
    if (w >= 64) return v;
    return v & ((1LL << w) - 1);
}
#define S_clk         0
#define S_rst         1
#define S_a           2
#define S_b           3
#define S_result      4
#define S_result_next 5
#define S_fsm         6
#define S_fsm_next    7

void module_eval_tasks(int64_t* s) {
    if (s[S_clk] == 1 && s[S_rst] == 0) {
        s[S_result_next] = mask(s[S_a] + s[S_b], 32);
    }
}
void module_update_regs(int64_t* s) {
    s[S_result] = s[S_result_next];
    s[S_fsm] = s[S_fsm_next];
}
int module_eval_decls(int64_t* s) { return 0; }
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, 'test.c')
        so_path = os.path.join(tmpdir, 'test.so')
        with open(c_path, 'w') as f:
            f.write(c_source)
        result = subprocess.run(
            ['gcc', '-O2', '-shared', '-fPIC', '-o', so_path, c_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip('gcc not available')

        port_map = {'clk': 0, 'rst': 1, 'a': 2, 'b': 3, 'result': 4}
        sig_map = {**port_map, 'result_next': 5, 'fsm': 6, 'fsm_next': 7}
        ev = CModelEvaluator(so_path, 8, port_map, sig_map)

        # Build mock model with Reg/Port attributes
        model = types.SimpleNamespace()
        clk_sig = types.SimpleNamespace(name='clk', width=1, tags=set())
        clk_sig.is_int = lambda: False
        rst_sig = types.SimpleNamespace(name='rst', width=1, tags=set())
        rst_sig.is_int = lambda: False
        model.clk = Reg(0, 1, clk_sig)
        model.rst = Reg(0, 1, rst_sig)

        a_sig = types.SimpleNamespace(name='a', width=32, tags=set())
        a_sig.is_int = lambda: False
        a_sig.is_input = lambda: True
        a_sig.is_output = lambda: False
        a_port = Port(None, None, None)
        a_port._set_value(Reg(0, 32, a_sig))
        model.a = a_port

        b_sig = types.SimpleNamespace(name='b', width=32, tags=set())
        b_sig.is_int = lambda: False
        b_sig.is_input = lambda: True
        b_sig.is_output = lambda: False
        b_port = Port(None, None, None)
        b_port._set_value(Reg(0, 32, b_sig))
        model.b = b_port

        r_sig = types.SimpleNamespace(name='result', width=32, tags=set())
        r_sig.is_int = lambda: False
        r_sig.is_input = lambda: False
        r_sig.is_output = lambda: True
        r_port = Port(None, None, None)
        r_port._set_value(Reg(0, 32, r_sig))
        model.result = r_port

        # Bind ports to buffer
        deferred = CModelEvaluator.bind_ports_to_buffer(model, ev._buf, port_map)
        ev._deferred_signals = deferred or []

        # Simulate testbench: write inputs
        model.a.wr(10)
        model.b.wr(20)

        # Simulate _period: clk=1, eval, clk=0
        model.rst.val = 0
        model.clk.val = 1
        ev.eval()
        model.clk.val = 0

        # Read output
        assert model.result.rd() == 30


def test_bind_ports_binds_submodel_ports():
    """bind_ports_to_buffer replaces sub-model (Handshake/Channel) Port values
    with CBufferSignal using sig_map with prefixed names."""
    import ctypes
    import types
    from polyphony.simulator import (
        CBufferSignal, CModelEvaluator, Model, Port, Reg, Net,
    )

    # Top-level model with clk/rst + a sub-model 'c' (like Handshake)
    model = types.SimpleNamespace()
    clk_sig = types.SimpleNamespace(name='clk', width=1, tags=set())
    clk_sig.is_int = lambda: False
    rst_sig = types.SimpleNamespace(name='rst', width=1, tags=set())
    rst_sig.is_int = lambda: False
    model.clk = Reg(0, 1, clk_sig)
    model.rst = Reg(0, 1, rst_sig)

    # Sub-model 'c' with data, valid, ready ports
    sub_core = types.SimpleNamespace()
    data_sig = types.SimpleNamespace(name='data', width=1, tags=set())
    data_sig.is_int = lambda: False
    data_sig.is_input = lambda: False
    data_sig.is_output = lambda: True
    data_port = Port(None, None, None)
    data_port._set_value(Net(0, 1, data_sig))
    sub_core.data = data_port

    valid_sig = types.SimpleNamespace(name='valid', width=1, tags=set())
    valid_sig.is_int = lambda: False
    valid_sig.is_input = lambda: False
    valid_sig.is_output = lambda: True
    valid_port = Port(None, None, None)
    valid_port._set_value(Net(0, 1, valid_sig))
    sub_core.valid = valid_port

    sub_core.hdlmodule = types.SimpleNamespace()
    sub_core._tasks = []
    sub_core._decls = []

    # Wrap as Model
    sub_model = Model()
    super(Model, sub_model).__setattr__("__model", sub_core)
    model.c = sub_model

    # Buffer: clk=0, rst=1, c_data=2, c_valid=3
    buf = (ctypes.c_int64 * 4)()
    port_map = {'clk': 0, 'rst': 1}
    sig_map = {'clk': 0, 'rst': 1, 'c_data': 2, 'c_data_next': 3, 'c_valid': 2, 'c_valid_next': 3}
    # Use separate indices for valid
    sig_map = {'clk': 0, 'rst': 1, 'c_data': 2, 'c_valid': 3}

    CModelEvaluator.bind_ports_to_buffer(model, buf, port_map, sig_map)

    # Sub-model Port values should now be CBufferSignal
    assert isinstance(sub_core.data.value, CBufferSignal)
    assert isinstance(sub_core.valid.value, CBufferSignal)

    # Writing to C buffer should be visible via Port.rd()
    buf[2] = 1
    assert sub_core.data.value.val == 1
    buf[3] = 1
    assert sub_core.valid.value.val == 1


def test_cbuffersignal_input_port_deferred_write():
    """Input port CBufferSignal with deferred=True does NOT write to buffer
    immediately. The write is held in _pending and flushed by flush_pending().

    This matches Python Reg's double-buffering: set() writes to next,
    update_regs copies next→val. Without this, the testbench's wr() would
    overwrite the current value before the C evaluator reads it.
    """
    import ctypes
    from polyphony.simulator import CBufferSignal

    buf = (ctypes.c_int64 * 4)()
    sig = CBufferSignal(buf, idx=0, width=32, is_signed=True, deferred=True)

    # Initial buffer value
    buf[0] = 100

    # set() should NOT change the buffer immediately
    sig.set(42)
    assert buf[0] == 100, "deferred CBufferSignal should not write to buffer on set()"

    # val should still read the buffer (current value)
    assert sig.val == 100

    # flush_pending() should write the pending value
    sig.flush_pending()
    assert buf[0] == 42
