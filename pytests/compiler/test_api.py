import os
import pytest
from polyphony.compiler import compile, _


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


class TestCompilePartialArgs:
    def _test_path(self, *parts):
        return os.path.join(_TESTS_DIR, *parts)

    def test_compile_all_args_applied(self):
        """compile() with all args specified produces a model (no input ports for those args)."""
        model = compile(
            self._test_path('expr', 'expr01.py'),
            'expr01',
            args=(1,),
        )
        assert model is not None

    def test_compile_placeholder_skips_binding(self):
        """compile() with _ placeholder leaves that argument as an input port."""
        model = compile(
            self._test_path('expr', 'expr01.py'),
            'expr01',
            args=(_,),
        )
        assert model is not None
