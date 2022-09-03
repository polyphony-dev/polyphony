#!/usr/bin/env python3
import argparse
import sys
import os
import traceback
import subprocess
import types


IVERILOG_PATH = 'iverilog'
ROOT_DIR = '.' + os.path.sep
TEST_DIR = ROOT_DIR + 'tests'
TMP_DIR  = ROOT_DIR + '.tmp'
sys.path.append(ROOT_DIR)

from polyphony.compiler.__main__ import compile_main, logging_setting
from polyphony.compiler.common.env import env


def parse_options():
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    parser = argparse.ArgumentParser(prog='simu')
    parser.add_argument('-C', dest='compile_only', action='store_true')
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


def exec_test(casefile_path, options=None):
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    if options.with_path_name:
        p, _ = os.path.splitext(casefile_path)
        options.output_prefix = p.replace('.', '').replace(os.path.sep, '_')
        casename = f'{options.output_prefix}_{casename}'
    else:
        options.output_prefix = ''

    if exec_compile(casefile_path, casename, options):
        finishes = []
        for testbench in env.testbenches:
            result_lines = simulate_verilog(testbench.base_name, casename, casefile_path, options)
            if result_lines:
                finishes.append(result_lines[-2])
        return finishes
    else:
        return None

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

def exec_compile(casefile_path, casename, simu_options):
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
    try:
        compile_main(casefile_path, compiler_options)
    except Exception as e:
        print('[COMPILE PYTHON] FAILED:' + casefile_path)
        if env.dev_debug_mode:
            traceback.print_exc()
        print(e)
        return False
    if simu_options.compile_only:
        return False
    return True


def simulate_verilog(testname, casename, casefile_path, options):
    if options.output_prefix:
        test_filename = f'{options.output_prefix}_{testname}'
    else:
        test_filename = testname
    hdl_files = [
        f'{TMP_DIR}{os.path.sep}{casename}.v',
        f'{TMP_DIR}{os.path.sep}{test_filename}.v',
    ]
    exec_name = '{}{}{}'.format(TMP_DIR, os.path.sep, test_filename)
    args = ('{} -I {} -W all -Wno-implicit-dimensions -o {} -s {}'.format(IVERILOG_PATH, TMP_DIR, exec_name, testname)).split(' ')
    args += hdl_files
    try:
        subprocess.check_call(args)
    except Exception as e:
        print('[COMPILE HDL] FAILED:' + casefile_path)
        return
    try:
        out = subprocess.check_output([exec_name])
        lines = out.decode('utf-8').split('\n')
        for line in lines:
            if options.debug_mode:
                print(line)
            if 'FAILED' in line:
                raise Exception()
        return lines
    except Exception as e:
        print('[SIMULATION] FAILED:' + casefile_path)
        print(e)
    return None


if __name__ == '__main__':
    options = parse_options()
    exec_test(options.source, options=options)
