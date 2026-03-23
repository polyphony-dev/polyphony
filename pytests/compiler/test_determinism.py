"""Determinism tests: same input must produce identical Verilog output regardless of PYTHONHASHSEED."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parents[2]
TESTS_DIR = REPO_ROOT / 'tests'


def compile_with_seed(source: Path, seed: int, outdir: Path) -> list[Path]:
    """Compile source with the given PYTHONHASHSEED and return generated .v file paths."""
    env = os.environ.copy()
    env['PYTHONHASHSEED'] = str(seed)
    result = subprocess.run(
        [sys.executable, '-m', 'polyphony.compiler', str(source), '-d', str(outdir)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f'Compilation failed (seed={seed}):\n{result.stderr}')
    return sorted(outdir.glob('*.v'))


def assert_same_output(source: Path) -> None:
    """Assert that compiling source with two different hash seeds yields identical .v files."""
    with tempfile.TemporaryDirectory() as d0, tempfile.TemporaryDirectory() as d1:
        dir0, dir1 = Path(d0), Path(d1)
        files0 = compile_with_seed(source, seed=0, outdir=dir0)
        files1 = compile_with_seed(source, seed=42, outdir=dir1)

        assert [f.name for f in files0] == [f.name for f in files1], (
            f'Different file sets produced for seed=0 vs seed=42 when compiling {source.name}'
        )
        for f0, f1 in zip(files0, files1):
            content0 = f0.read_text()
            content1 = f1.read_text()
            assert content0 == content1, (
                f'{f0.name} differs between seed=0 and seed=42 when compiling {source.name}.\n'
                f'First difference around:\n'
                + _first_diff(content0, content1)
            )


def _first_diff(a: str, b: str) -> str:
    lines_a = a.splitlines()
    lines_b = b.splitlines()
    for i, (la, lb) in enumerate(zip(lines_a, lines_b)):
        if la != lb:
            return f'  line {i + 1}:\n  seed=0:  {la!r}\n  seed=42: {lb!r}'
    return f'(lengths differ: {len(lines_a)} vs {len(lines_b)} lines)'


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    def test_inline_function_determinism(self):
        """Inlined function expansion must be deterministic regardless of hash seed."""
        assert_same_output(TESTS_DIR / 'func' / 'func06.py')

    def test_class_method_determinism(self):
        """Class method compilation must be deterministic."""
        assert_same_output(TESTS_DIR / 'class' / 'class01.py')

    def test_module_worker_determinism(self):
        """Module with workers must produce deterministic output."""
        assert_same_output(TESTS_DIR / 'issues' / 'busy_loop.py')

    def test_xor_nn_determinism(self):
        """Complex module with inlining, constant propagation, and SSA must be deterministic."""
        assert_same_output(TESTS_DIR / 'issues' / 'xor_nn.py')
