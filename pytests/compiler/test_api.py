import importlib.util
import os
import pytest
from polyphony.compiler import compile


_TESTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'tests')
_API_SOURCES_DIR = os.path.join(os.path.dirname(__file__), 'api_test_sources')


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

    def test_compile_params_bind_int(self):
        """params で int 値を渡してシミュレーションで検証。"""
        from polyphony.simulator import Simulator

        src = os.path.join(_API_SOURCES_DIR, 'param_int.py')
        model = compile(src, 'param_int', params={'width': 42})
        assert model is not None
        with Simulator(model):
            assert model.p.rd() == 42

    def test_compile_params_bind_type(self):
        """params で型を渡してシミュレーションで検証。"""
        from polyphony.simulator import Simulator
        from polyphony.typing import int8

        src = os.path.join(_API_SOURCES_DIR, 'param_type.py')
        model = compile(src, 'param_type', params={'dtype': int8})
        assert model is not None
        with Simulator(model):
            assert model.p.rd() == 10

    def test_compile_params_bind_tuple(self):
        """params で tuple を渡してシミュレーションで検証。"""
        from polyphony.simulator import Simulator
        from polyphony.timing import wait_value

        src = os.path.join(_API_SOURCES_DIR, 'param_tuple.py')
        model = compile(src, 'param_tuple', params={'base': 10, 'offsets': (1, 2)})
        assert model is not None
        with Simulator(model):
            wait_value(13, model.o)
            assert model.o.rd() == 13

    def test_compile_params_bind_func(self):
        """params で関数を渡してシミュレーションで検証。"""
        from polyphony.simulator import Simulator
        from polyphony.timing import wait_value
        import importlib.util

        src = os.path.join(_API_SOURCES_DIR, 'param_func.py')
        spec = importlib.util.spec_from_file_location('param_func', src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        model = compile(src, 'param_func', params={'fn': mod.compute})
        assert model is not None
        with Simulator(model):
            wait_value(42, model.o)
            assert model.o.rd() == 42


def _load_class(name, path):
    """Load a class from a .py file by name."""
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, name)


class TestCompileObjectPass:
    """Tests for passing Python class/function objects directly to compile()."""

    def test_compile_class_object(self):
        """compile(ClassObj, params={...}) works like compile(path, name, params={...})."""
        from polyphony.simulator import Simulator

        src = os.path.join(_API_SOURCES_DIR, 'object_pass.py')
        cls = _load_class('object_pass', src)
        model = compile(cls, params={'width': 99})
        assert model is not None
        with Simulator(model):
            assert model.p.rd() == 99

    def test_compile_class_object_without_params(self):
        """compile(ClassObj) without params returns a model."""
        src = os.path.join(_API_SOURCES_DIR, 'param_int.py')
        cls = _load_class('param_int', src)
        model = compile(cls, params={'width': 7})
        assert model is not None

    def test_compile_class_explicit_target_ignored(self):
        """When source is an object, target is derived from __name__, explicit target is ignored."""
        from polyphony.simulator import Simulator

        src = os.path.join(_API_SOURCES_DIR, 'object_pass.py')
        cls = _load_class('object_pass', src)
        model = compile(cls, target='ignored', params={'width': 99})
        assert model is not None
        with Simulator(model):
            assert model.p.rd() == 99

    def test_compile_string_without_target_raises(self):
        """compile(path_str) without target raises ValueError."""
        src = os.path.join(_API_SOURCES_DIR, 'object_pass.py')
        with pytest.raises(ValueError, match='target'):
            compile(src)


class TestModuleClassParamsValidation:
    """Tests for module class params validation."""

    def test_module_class_without_params_raises(self):
        """compile(ModuleClass) without params raises ValueError."""
        src = os.path.join(_API_SOURCES_DIR, 'object_pass.py')
        cls = _load_class('object_pass', src)
        with pytest.raises(ValueError, match='params'):
            compile(cls)

    def test_module_class_with_missing_params_raises(self):
        """compile(ModuleClass, params={}) with missing required params raises ValueError."""
        src = os.path.join(_API_SOURCES_DIR, 'object_pass.py')
        cls = _load_class('object_pass', src)
        with pytest.raises(ValueError, match='width'):
            compile(cls, params={})

    def test_module_class_string_without_params_raises(self):
        """compile(path, name) for module class without params raises ValueError."""
        src = os.path.join(_API_SOURCES_DIR, 'object_pass.py')
        with pytest.raises(ValueError, match='params'):
            compile(src, 'object_pass')

    def test_module_class_string_with_missing_params_raises(self):
        """compile(path, name, params={}) for module class with missing params raises ValueError."""
        src = os.path.join(_API_SOURCES_DIR, 'object_pass.py')
        with pytest.raises(ValueError, match='width'):
            compile(src, 'object_pass', params={})

    def test_function_without_params_ok(self):
        """compile() for a function without params is fine (args become input ports)."""
        model = compile(
            os.path.join(_TESTS_DIR, 'expr', 'expr01.py'),
            'expr01',
        )
        assert model is not None


class TestCompileTypes:
    """Tests for types parameter to specify argument types."""

    def test_types_sets_argument_type(self):
        """compile() with types sets the bit width of unannotated arguments."""
        from polyphony.simulator import Simulator
        from polyphony.typing import int8
        from polyphony.timing import clkfence

        src = os.path.join(_API_SOURCES_DIR, 'typed_func.py')
        model = compile(src, 'typed_func', types={'a': int8, 'b': int8})
        assert model is not None
        core = getattr(model, '__model')
        with Simulator(model):
            core.typed_func_i8i8_in_a.set(3)
            core.typed_func_i8i8_in_b.set(4)
            core.typed_func_i8i8_ready.set(1)
            clkfence()
            core.typed_func_i8i8_ready.set(0)
            for _ in range(20):
                if core.typed_func_i8i8_valid.val == 1:
                    break
                clkfence()
            assert core.typed_func_i8i8_out_0.val == 7
            core.typed_func_i8i8_accept.set(1)
            clkfence()

    def test_types_conflict_with_annotation_raises(self):
        """compile() with types that conflict with existing annotations raises ValueError."""
        from polyphony.typing import int8, int32

        src = os.path.join(_API_SOURCES_DIR, 'annotated_func.py')
        with pytest.raises(ValueError, match='already has type annotation'):
            compile(src, 'annotated_func', types={'a': int32})

    def test_types_same_as_annotation_ok(self):
        """compile() with types matching existing annotations is fine."""
        from polyphony.typing import int16

        src = os.path.join(_API_SOURCES_DIR, 'annotated_func.py')
        model = compile(src, 'annotated_func', types={'a': int16, 'b': int16})
        assert model is not None

    def test_types_unknown_param_raises(self):
        """compile() with types for non-existent parameter raises ValueError."""
        from polyphony.typing import int8

        src = os.path.join(_API_SOURCES_DIR, 'typed_func.py')
        with pytest.raises(ValueError, match='no_such_param'):
            compile(src, 'typed_func', types={'no_such_param': int8})

    def test_types_python_builtin_int(self):
        """compile() with types={...: int} uses default int width."""
        src = os.path.join(_API_SOURCES_DIR, 'typed_func.py')
        model = compile(src, 'typed_func', types={'a': int, 'b': int})
        assert model is not None

    def test_types_with_model_call(self):
        """compile() with types + model(args) direct call works."""
        from polyphony.simulator import Simulator

        src = os.path.join(_API_SOURCES_DIR, 'typed_func.py')
        model = compile(src, 'typed_func', types={'a': int, 'b': int})
        with Simulator(model):
            assert model(3, 4) == 7
            assert model(10, 20) == 30

    @pytest.mark.xfail(reason="compiler does not support list type as function argument")
    def test_types_list(self):
        """compile() with types={...: List[int8]} specifies list element type."""
        from polyphony.typing import List, int8

        src = os.path.join(_API_SOURCES_DIR, 'typed_list_func.py')
        model = compile(src, 'typed_list_func', types={'data': List[int8][4]})
        assert model is not None


class TestModelCall:
    """Tests for model(args) direct function call."""

    def test_model_call_positional(self):
        """model(a, b) calls the function with positional args."""
        from polyphony.simulator import Simulator

        src = os.path.join(_API_SOURCES_DIR, 'typed_func.py')
        model = compile(src, 'typed_func', types={'a': int, 'b': int})
        with Simulator(model):
            assert model(1, 2) == 3
            assert model(100, 200) == 300

    def test_model_call_kwargs(self):
        """model(a=1, b=2) calls the function with keyword args."""
        from polyphony.simulator import Simulator

        src = os.path.join(_API_SOURCES_DIR, 'typed_func.py')
        model = compile(src, 'typed_func', types={'a': int, 'b': int})
        with Simulator(model):
            assert model(a=5, b=10) == 15

    def test_model_call_with_params(self):
        """model(a) works with partially applied params."""
        from polyphony.simulator import Simulator

        model = compile(
            os.path.join(_TESTS_DIR, 'expr', 'expr01.py'),
            'expr01',
            params={'a': 5},
        )
        with Simulator(model):
            # expr01(a) = a + 1 + 1, with a=5 bound → no input args
            assert model() == 7
