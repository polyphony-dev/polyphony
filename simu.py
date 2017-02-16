#!/usr/bin/env python3
import sys
import os
import traceback
import subprocess

IVERILOG_PATH = 'iverilog'
ROOT_DIR = './'
TEST_DIR = ROOT_DIR + 'tests'
TMP_DIR  = ROOT_DIR + '.tmp'
sys.path.append(ROOT_DIR)

from polyphony.compiler.__main__ import compile_main, logging_setting
from polyphony.compiler.env import env


def exec_test(casefile_path, output=True, compile_only=False):
    compile_only = False
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    try:
        compile_main(casefile_path, casename, TMP_DIR, debug_mode=output)
    except Exception as e:
        print('[COMPILE PYTHON] FAILED:' + casefile_path)
        if env.dev_debug_mode:
            traceback.print_exc()
        print(e)
        return
    if compile_only:
        return
    for testbench in env.testbenches:
        simulate_verilog(testbench.orig_name, casename, casefile_path, output)


def simulate_verilog(testname, casename, casefile_path, output):
    hdl_files = ['{}/{}.v'.format(TMP_DIR, casename), '{}/{}_{}.v'.format(TMP_DIR, casename, testname)]
    exec_name = '{}/{}'.format(TMP_DIR, testname)
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
    except Exception as e:
        print('[SIMULATION] FAILED:' + casefile_path)
        print(e)


if __name__ == '__main__':
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    if len(sys.argv) > 1:
        # import profile
        # profile.run("exec_test(sys.argv[1])")
        exec_test(sys.argv[1])
