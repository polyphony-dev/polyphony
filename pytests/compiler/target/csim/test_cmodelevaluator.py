import ctypes
import os
import subprocess
import tempfile
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
