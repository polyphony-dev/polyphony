import types
import inspect
import sys
from .common.common import read_source
from .common.env import env
from .__main__ import setup, compile_plan
from .__main__ import compile as compile_polyphony
from .ahdl.ahdl import *


def from_python(src_file, target_name, args):
    from ..simulator import SimulationModelBuilder

    options = types.SimpleNamespace()
    options.output_name = ''
    options.output_dir = ''
    options.verbose_level = 0
    options.quiet_level = 0
    options.config = None
    options.debug_mode = False
    options.verilog_dump = False
    options.verilog_monitor = False
    options.targets = [(target_name, args)]
    setup(src_file, options)
    source_text = read_source(src_file)
    scopes = compile_polyphony(compile_plan(), source_text, src_file)

    main_py_module = types.ModuleType('__main__')
    code_obj = compile(source_text, src_file, 'exec')
    exec(code_obj, main_py_module.__dict__)
    py_module_class = main_py_module.__dict__[target_name]

    model = None
    for s in scopes:
        if s.orig_base_name != target_name:
            continue
        hdlmodule = env.hdlscope(s)
        #print(hdlmodule)
        model = SimulationModelBuilder().build_model(hdlmodule, main_py_module)
        break
    return model

def from_module(module_class, args):
    target = module_class
    pymodule = module_class(*args)
    source = inspect.getfile(target)
    return from_python(source, target.__name__, args, pymodule)

def import_module(code, filename):
    module = types.ModuleType('polyphony_internal_imported_module')
    exec(code, module.__dict__)
    return module

def from_object(object):
    print(vars(object))
