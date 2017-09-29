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
from polyphony.compiler.env import env


def exec_test(casefile_path, output=True, compile_only=False, extra=None):
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    options = types.SimpleNamespace()
    options.output_name = casename
    options.output_dir = TMP_DIR
    options.verbose_level = 0
    options.quiet_level = 0
    options.debug_mode = output
    if extra:
        options.verilog_dump = extra.verilog_dump
        options.verilog_monitor = extra.verilog_monitor
    else:
        options.verilog_dump = False
        options.verilog_monitor = False
    try:
        compile_main(casefile_path, options)
    except Exception as e:
        print('[COMPILE PYTHON] FAILED:' + casefile_path)
        if env.dev_debug_mode:
            traceback.print_exc()
        print(e)
        return
    if compile_only:
        return
    finishes = []
    for testbench in env.testbenches:
        result_lines = simulate_verilog(testbench.orig_name, casename, casefile_path, output)
        if result_lines:
            finishes.append(result_lines[-2])
    return finishes


def simulate_verilog(testname, casename, casefile_path, output):
    hdl_files = ['{}{}{}.v'.format(TMP_DIR, os.path.sep, casename), '{}{}{}.v'.format(TMP_DIR, os.path.sep, testname)]
    exec_name = '{}{}{}'.format(TMP_DIR, os.path.sep, testname)
    args = ('{} -I {} -W all -o {} -s {}'.format(IVERILOG_PATH, TMP_DIR, exec_name, testname)).split(' ')
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
            if output:
                print(line)
            if 'FAILED' in line:
                raise Exception()
        return lines
    except Exception as e:
        print('[SIMULATION] FAILED:' + casefile_path)
        print(e)
    return None


if __name__ == '__main__':
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    parser = argparse.ArgumentParser(prog='simu')
    parser.add_argument('-vd', '--verilog_dump', dest='verilog_dump',
                        action='store_true', help='output vcd file in testbench')
    parser.add_argument('-vm', '--verilog_monitor', dest='verilog_monitor',
                        action='store_true', help='enable $monitor in testbench')
    parser.add_argument('source', help='Python source file')
    options = parser.parse_args()
    exec_test(options.source, extra=options)
