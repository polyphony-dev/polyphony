import types
import inspect
import sys
from .common.common import read_source
from .common.env import env
from .__main__ import setup, compile_plan
from .__main__ import compile as compile_polyphony
from .ahdl.ahdl import *


def from_python(src_file, target_name, args, module_instance=None):
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
    main_source = read_source(src_file)
    if not module_instance:
        m = import_module(main_source, src_file)
        py_module_class = getattr(m, target_name)
        if inspect.isclass(py_module_class):
            # TODO:
            py_args = [None] * len(args)
            py_module_instance = py_module_class(*py_args)
        elif inspect.isfunction(py_module_class):
            py_module_instance = None
        else:
            raise ValueError('module_instance is not a valid type')
    else:
        py_module_instance = module_instance
    scopes = compile_polyphony(compile_plan(), main_source, src_file)
    model = None
    for s in scopes:
        if s.orig_base_name != target_name:
            continue
        hdlmodule = env.hdlscope(s)
        #print(hdlmodule)
        model = SimulationModelBuilder().build(hdlmodule, py_module_instance)
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
