import builtins
import inspect
import os
import types
from collections.abc import Callable

from .common.common import read_source
from .common.env import env
from .__main__ import setup, compile_plan, output_plan, output_hdl
from .__main__ import compile as _compile_ir


def _validate_module_class_params(cls, params):
    """Validate that all required __init__ params are provided for a @module class."""
    if not getattr(cls, '_is_module', False):
        return
    sig = inspect.signature(cls.__init__)
    required = [
        name for name, p in sig.parameters.items()
        if name != 'self' and p.default is inspect.Parameter.empty
    ]
    if not required:
        return
    missing = [name for name in required if name not in params]
    if missing:
        raise ValueError(
            f"module class '{cls.__name__}' requires params for constructor arguments: "
            f"{', '.join(missing)}"
        )


def _validate_module_class_params_from_source(src_file, target, params):
    """Validate module class params when source is a file path string."""
    source_text = read_source(src_file)
    tmp_module = types.ModuleType('_polyphony_validation_tmp')
    code_obj = builtins.compile(source_text, src_file, 'exec')
    exec(code_obj, tmp_module.__dict__)
    cls = getattr(tmp_module, target, None)
    if cls is not None and inspect.isclass(cls):
        _validate_module_class_params(cls, params)


def compile(
    source: str | type | Callable,
    target: str = '',
    params: dict | None = None,
    module_name: str = '',
    output_file: str = '',
):
    """Compile a Python source file or object to a simulation model.

    Args:
        source: Path to the Python source file, or a class/function object.
                When a class or function is passed, the source file is
                resolved via inspect.getfile() and the target name is
                derived from the object's __name__.
        target: Name of the function or class to compile.
                Required when source is a file path string.
                Ignored when source is a class or function object.
        params: Named parameters to apply. Keys are parameter names,
                values are constants for binding. Parameters not included
                remain as HDL input ports (for functions).
                For module classes, all constructor args must be specified.
        module_name: Output module name (auto-generated if empty).
        output_file: Verilog output file path (no output if empty).

    Returns:
        A simulation Model object.
    """
    from ..simulator import SimulationModelBuilder

    if isinstance(source, str):
        src_file = source
        if not target:
            raise ValueError("'target' is required when 'source' is a file path string")
    else:
        src_file = inspect.getfile(source)
        target = source.__name__

    if params is None:
        params = {}

    # Validate module class params
    if not isinstance(source, str):
        _validate_module_class_params(source, params)
    else:
        _validate_module_class_params_from_source(src_file, target, params)

    options = types.SimpleNamespace()
    options.output_name = module_name if module_name else os.path.splitext(os.path.basename(src_file))[0]
    options.output_dir = os.path.dirname(output_file) if output_file else ''
    options.output_prefix = ''
    options.verbose_level = 0
    options.quiet_level = 0
    options.config = None
    options.debug_mode = False
    options.hdl_debug_mode = False
    options.verilog_dump = False
    options.verilog_monitor = False
    options.targets = [(target, params)]

    setup(src_file, options)
    source_text = read_source(src_file)

    plan = compile_plan()
    scopes = _compile_ir(plan, source_text, src_file)

    if output_file:
        if not options.output_dir:
            options.output_dir = os.path.dirname(os.path.abspath(output_file))
        options.output_name = os.path.splitext(os.path.basename(output_file))[0]
        output_hdl(output_plan(), scopes, options, stage_offset=len(plan))

    main_py_module = types.ModuleType('__main__')
    code_obj = builtins.compile(source_text, src_file, 'exec')
    exec(code_obj, main_py_module.__dict__)

    model = None
    for s in scopes:
        if s.orig_base_name != target:
            continue
        hdlmodule = env.hdlscope(s)
        model = SimulationModelBuilder().build_model(hdlmodule, main_py_module)
        break

    env.destroy()
    return model
