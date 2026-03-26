import builtins
import os
import types

from .common.common import read_source
from .common.env import env
from .__main__ import setup, compile_plan, output_plan, output_hdl
from .__main__ import compile as _compile_ir


def compile(
    source: str,
    target: str,
    args: tuple = (),
    module_name: str = '',
    output_file: str = '',
):
    """Compile a Python source file to a simulation model.

    Args:
        source: Path to the Python source file.
        target: Name of the function or class to compile.
        args: Constructor/function arguments (constants).
        module_name: Output module name (auto-generated if empty).
        output_file: Verilog output file path (no output if empty).

    Returns:
        A simulation Model object.
    """
    from ..simulator import SimulationModelBuilder

    args_str = tuple(str(a) for a in args)

    options = types.SimpleNamespace()
    options.output_name = module_name if module_name else os.path.splitext(os.path.basename(source))[0]
    options.output_dir = os.path.dirname(output_file) if output_file else ''
    options.output_prefix = ''
    options.verbose_level = 0
    options.quiet_level = 0
    options.config = None
    options.debug_mode = False
    options.hdl_debug_mode = False
    options.verilog_dump = False
    options.verilog_monitor = False
    options.targets = [(target, args_str)]

    setup(source, options)
    source_text = read_source(source)

    plan = compile_plan()
    scopes = _compile_ir(plan, source_text, source)

    if output_file:
        if not options.output_dir:
            options.output_dir = os.path.dirname(os.path.abspath(output_file))
        options.output_name = os.path.splitext(os.path.basename(output_file))[0]
        output_hdl(output_plan(), scopes, options, stage_offset=len(plan))

    main_py_module = types.ModuleType('__main__')
    code_obj = builtins.compile(source_text, source, 'exec')
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
