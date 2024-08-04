#!/usr/bin/env python3
import argparse
import sys
import os
import re
import traceback
import subprocess
import types
import inspect
IVERILOG_PATH = 'iverilog'
ROOT_DIR = '.' + os.path.sep
TEST_DIR = ROOT_DIR + 'tests'
TMP_DIR  = ROOT_DIR + '.tmp'
sys.path.append(ROOT_DIR)

from polyphony.compiler.__main__ import compile_main, logging_setting
from polyphony.compiler.common.env import env
from polyphony.compiler.common.common import read_source
from polyphony.compiler.__main__ import setup, compile_plan, output_hdl, output_plan
from polyphony.compiler.__main__ import compile as compile_polyphony
from polyphony.simulator import Simulator, SimulationModelBuilder, HDLAssertionError

def parse_options():
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    parser = argparse.ArgumentParser(prog='simu')
    parser.add_argument('-C', dest='compile_only', action='store_true')
    parser.add_argument('-P', '--python', dest='enable_python', action='store_true',
                        default=False, help='enable python simulation')
    parser.add_argument('-c', '--config', dest='config',
                        metavar='CONFIG', help='set configration(json literal or file)')
    parser.add_argument('-dd', '--diable_debug', dest='debug_mode',
                        action='store_false', default=True, help='disable debug mode')
    parser.add_argument('-vd', '--verilog_dump', dest='verilog_dump',
                        action='store_true', help='output vcd file in testbench')
    parser.add_argument('-vm', '--verilog_monitor', dest='verilog_monitor',
                        action='store_true', help='enable $monitor in testbench')
    parser.add_argument('-p', dest='with_path_name', action='store_true')
    parser.add_argument('-t', '--targets', nargs='+', dest='targets', default=list())
    parser.add_argument('source', help='Python source file')
    return parser.parse_args()


def case_name_from_path(casefile_path):
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    return casename


def exec_test(casefile_path, simu_options):
    casename = case_name_from_path(casefile_path)
    if simu_options.with_path_name:
        p, _ = os.path.splitext(casefile_path)
        simu_options.output_prefix = p.replace('.', '').replace(os.path.sep, '_')
        casename = f'{simu_options.output_prefix}_{casename}'
    else:
        simu_options.output_prefix = ''

    compiler_options = setup_compiler(casefile_path, casename, simu_options)
    source_text = read_source(casefile_path)

    scopes = exec_compile(casefile_path, source_text, compiler_options, simu_options)
    if not scopes:
        return ['Compile Error'], []

    hdl_finishes = simulate_on_verilog(casename, casefile_path, simu_options)
    if simu_options.enable_python:
        py_finishes = simulate_on_python(casefile_path, source_text, scopes, simu_options)
    else:
        py_finishes = []
    return hdl_finishes, py_finishes


def targets_from_source_comment(filepath):
    targets = []
    file = open(filepath, 'r')
    for line in file.readlines():
        if not line.startswith('# TEST '):
            continue
        terms = line[:-1].split(' ')
        if len(terms) <= 2:
            continue
        targets.append((terms[2], terms[3:]))
    return targets


def setup_compiler(casefile_path, casename, simu_options):
    assert simu_options
    compiler_options = types.SimpleNamespace()
    compiler_options.output_name = casename
    compiler_options.output_prefix = simu_options.output_prefix
    compiler_options.output_dir = TMP_DIR
    compiler_options.verbose_level = 0
    compiler_options.quiet_level = 0 if simu_options.debug_mode else 3
    if hasattr(simu_options, 'targets'):
        compiler_options.targets = simu_options.targets
    else:
        compiler_options.targets = targets_from_source_comment(casefile_path)
    compiler_options.config = simu_options.config
    compiler_options.debug_mode = simu_options.debug_mode
    compiler_options.verilog_dump = simu_options.verilog_dump
    compiler_options.verilog_monitor = simu_options.verilog_monitor
    setup(casefile_path, compiler_options)
    return compiler_options


def exec_compile(casefile_path, source_text, compiler_options, simu_options):
    try:
        plan = compile_plan()
        scopes = compile_polyphony(plan, source_text, casefile_path)
        output_hdl(output_plan(), scopes, compiler_options, stage_offset=len(plan))
    except Exception as e:
        print(f'[COMPILE PYTHON] FAILED: {casefile_path}')
        if env.dev_debug_mode:
            traceback.print_exc()
        print(e)
        return None
    if simu_options.compile_only:
        return None
    return scopes


def simulate_on_verilog(casename, casefile_path, simu_options):
    hdl_finishes = []
    for testbench in env.testbenches:
        result_lines = call_iverilog(testbench.base_name, casename, casefile_path, simu_options)
        if result_lines:
            # result_lines[-2] == '***:finish'
            hdl_finishes.append(result_lines[-2])
        else:
            hdl_finishes.append('FAIL')
    return hdl_finishes


def call_iverilog(testname, casename, casefile_path, options):
    if options.output_prefix:
        test_filename = f'{options.output_prefix}_{testname}'
    else:
        test_filename = testname
    hdl_files = [
        f'{TMP_DIR}{os.path.sep}{casename}.v',
        f'{TMP_DIR}{os.path.sep}{test_filename}.v',
    ]
    exec_name = f'{TMP_DIR}{os.path.sep}{test_filename}'
    args = (f'{IVERILOG_PATH} -I {TMP_DIR} -W all -Wno-implicit-dimensions -o {exec_name} -s {testname}').split(' ')
    args += hdl_files
    try:
        subprocess.check_call(args)
    except Exception as e:
        print(f'[COMPILE HDL] FAILED: {casefile_path}')
        return
    try:
        out = subprocess.check_output([exec_name], timeout=3)
        lines = out.decode('utf-8').split('\n')
        for line in lines:
            if options.debug_mode:
                print(line)
            if 'FAILED' in line:
                raise Exception()
        return lines
    except Exception as e:
        print(f'[HDL SIMULATION] FAILED: {casefile_path}')
        print(e)
    return None


def model_selector_with_argv(models):
    def model_selector(*args, **kwargs):
        args_str = []
        for a in args:
            if type(a).__name__ == 'type':
                args_str.append(a.__name__)
            else:
                args_str.append(str(a))
        for model, hdlmodule in models.values():
            if args_str == hdlmodule.scope._bound_args:
                return model
        raise ValueError('model not found')
    return model_selector


def model_selector_with_argtypes(models, name):
    def model_selector(*args, **kwargs):
        arg_types = []
        for a in args:
            if isinstance(a, bool):
                arg_types.append('b')
            elif isinstance(a, int):
                arg_types.append('i')
            else:
                assert False, f'unsupported arg type: {type(a)}'
        kwarg_types = {}
        for k, v in kwargs.items():
            if isinstance(v, bool):
                kwarg_types[k] = 'b'
            elif isinstance(v, int):
                kwarg_types[k] = 'i'
            else:
                assert False, f'unsupported arg type: {type(v)}'
        for model, hdlmodule in models.values():
            if hdlmodule.name == name and not arg_types and not kwarg_types:
                return model()
            names = hdlmodule.name.rsplit('_', 1)
            orig_name = names[0]
            if orig_name != name:
                continue
            if len(names) == 1 and not arg_types:
                return model(*args, **kwargs)
            a_types = arg_types[:]
            module_arg_types = re.findall(r'i|b', names[-1])
            if kwarg_types:
                for param_name in hdlmodule.scope.param_names():
                    if param_name in kwarg_types:
                        a_types.append(kwarg_types[param_name])
            if len(a_types) < len(module_arg_types):
                values = hdlmodule.scope.param_default_values()
                offs = len(a_types)
                for v in values[offs:]:
                    if isinstance(a, bool):
                        a_types.append('b')
                    elif isinstance(a, int):
                        a_types.append('i')
                    else:
                        # no default value
                        break
            if a_types == module_arg_types:
                return model(*args, **kwargs)
        raise ValueError('model not found')
    return model_selector


import sys
from io import StringIO
import contextlib

def simulate_on_python(casefile_path, source_text, scopes, simu_options):
    finishes = []
    casename = case_name_from_path(casefile_path)
    main_py_module = types.ModuleType('__main__')
    try:
        code_obj = compile(source_text, casefile_path, 'exec')
        casefile_dir = os.path.dirname(casefile_path)
        sys.path.append(casefile_dir)
        exec(code_obj, main_py_module.__dict__)
    except Exception as e:
        print(e)
        finishes.append('FAIL')
        return finishes
    py_objects = []
    for key, value in vars(main_py_module).items():
        if key.startswith(casename):
            py_objects.append(value)

    for testbench in env.testbenches:
        test = getattr(main_py_module, testbench.base_name)
        if not test:
            continue
        models = {}
        test_hdlmodule = env.hdlscope(testbench)
        for _, sub_hdlmodule, _, _ in test_hdlmodule.sub_modules.values():
            if sub_hdlmodule.name in models:
                continue
            model = SimulationModelBuilder().build_model(sub_hdlmodule, main_py_module, is_top=True)
            models[sub_hdlmodule.name] = (model, sub_hdlmodule)
        # Replacing classes/functions under test with a model selector
        for obj in py_objects:
            if inspect.isclass(obj):
                test._orig_func.__globals__[obj.__name__] = model_selector_with_argv(models)
            elif inspect.isfunction(obj):
                test._orig_func.__globals__[obj.__name__] = model_selector_with_argtypes(models, obj.__name__)
            else:
                assert False
        # exec test
        try:
            simulate_models = [model for model, _ in models.values()]
            test._orig_func._execute_on_simu = True
            with Simulator(simulate_models):
                test()
            finishes.append('OK')
        except HDLAssertionError as e:  # from hdlmodule code
            print(f'ASSERTION FAILED: {e.args[0]}')
            print('[PYTHON SIMULATION] FAILED:' + casefile_path)
            finishes.append('FAIL')
        except AssertionError as e:  # from python test code
            _, _, tb = sys.exc_info()
            tb_info = traceback.extract_tb(tb)
            filename, line, _, code = tb_info[-1]
            if filename == casefile_path:
                print(f'ASSERTION FAILED: {casename}.py:{line} {code}')
                print(f'[PYTHON SIMULATION] FAILED: {filename}')
            else:
                print(f'[PYTHON SIMULATION] INTERNAL ERROR: {filename}:{line} {code}')
                traceback.print_exc()
            finishes.append('FAIL')
        except Exception as e:
            _, _, tb = sys.exc_info()
            tb_info = traceback.extract_tb(tb)
            filename, line, _, code = tb_info[-1]
            print(f'[PYTHON SIMULATION] INTERNAL ERROR: {filename}:{line} {code}')
            traceback.print_exc()
            finishes.append('FAIL')
    return finishes


if __name__ == '__main__':
    options = parse_options()
    hdl, py = exec_test(options.source, simu_options=options)
    hdl_success = True if '' not in hdl and 'FAIL' not in hdl else False
    py_success = True if not options.enable_python or ('' not in py and 'FAIL' not in py) else False
    if hdl_success and py_success:
        print('OK')
