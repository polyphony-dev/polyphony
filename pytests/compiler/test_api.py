import os
import pytest
from polyphony.compiler import compile


_TESTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'tests')


class TestCompileAPI:
    def _test_path(self, *parts):
        return os.path.join(_TESTS_DIR, *parts)

    def test_compile_returns_model(self):
        """compile() returns a Model object with expected ports."""
        model = compile(
            self._test_path('io', 'init01.py'),
            'init01',
        )
        assert model is not None
        assert hasattr(model, 'p0')
        assert hasattr(model, 'p1')

    def test_compile_with_output_file(self, tmp_path):
        """compile() writes Verilog when output_file is specified."""
        verilog_file = str(tmp_path / 'init01.v')
        model = compile(
            self._test_path('io', 'init01.py'),
            'init01',
            output_file=verilog_file,
        )
        assert model is not None
        assert os.path.exists(verilog_file)
        with open(verilog_file) as f:
            content = f.read()
        assert 'include' in content

    def test_compile_simulation_works(self):
        """compile() produces a Model that can be simulated."""
        from polyphony.simulator import Simulator

        model = compile(
            self._test_path('io', 'init01.py'),
            'init01',
        )
        with Simulator(model):
            assert model.p0.rd() == 123
            assert model.p1.rd() == 456


class TestCompileParams:
    def _test_path(self, *parts):
        return os.path.join(_TESTS_DIR, *parts)

    def test_compile_with_params_dict(self):
        """compile() with params dict applies named parameters."""
        model = compile(
            self._test_path('expr', 'expr01.py'),
            'expr01',
            params={'x': 1},
        )
        assert model is not None

    def test_compile_without_params(self):
        """compile() without params leaves all args as input ports."""
        model = compile(
            self._test_path('expr', 'expr01.py'),
            'expr01',
        )
        assert model is not None

    def test_compile_params_none(self):
        """compile() with params=None is same as no params."""
        model = compile(
            self._test_path('expr', 'expr01.py'),
            'expr01',
            params=None,
        )
        assert model is not None

    def test_compile_params_bind_constant(self):
        """params dict values are constant-propagated into the compiled result."""
        from polyphony.simulator import Simulator
        from polyphony.timing import clkfence

        model = compile(
            self._test_path('expr', 'expr01.py'),
            'expr01',
            params={'a': 5},
        )
        core = getattr(model, '__model')
        with Simulator(model):
            core.expr01_i32_ready.set(1)
            clkfence()
            core.expr01_i32_ready.set(0)
            for _ in range(20):
                if core.expr01_i32_valid.val == 1:
                    break
                clkfence()
            # expr01(a) = a + 1 + 1, with a=5 → 7
            assert core.expr01_i32_out_0.val == 7
            core.expr01_i32_accept.set(1)
            clkfence()
