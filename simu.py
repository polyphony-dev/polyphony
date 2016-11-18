#!/usr/bin/env python3
import sys
import os
import traceback
import logging
from subprocess import call, check_call, check_output

ROOT_DIR = './'
TEST_DIR = ROOT_DIR+'tests'
TMP_DIR  = ROOT_DIR+'.tmp'
sys.path.append(ROOT_DIR)
from polyphony.compiler.__main__ import compile_main, logging_setting
from polyphony.compiler.env import env


def exec_test(test, output=True, compile_only=False):
    casefile = os.path.basename(test)
    casename, _ = os.path.splitext(casefile)
    try:
        compile_main(test, casename, TMP_DIR)
    except Exception as e:
        print('[COMPILE PYTHON] FAILED:'+test)
        if env.dev_debug_mode:
            traceback.print_exc()
        print(e)
        return
    if compile_only:
        return

    hdl_files = ['{}/{}.v'.format(TMP_DIR, casename), '{}/{}_test.v'.format(TMP_DIR, casename)]
    exec_name = '{}/test'.format(TMP_DIR)
    args = ('iverilog -I {} -W all -o {} -s test'.format(TMP_DIR, exec_name)).split(' ')
    args += hdl_files
    try:
        check_call(args)
    except Exception as e:
        print('[COMPILE HDL] FAILED:'+test)
        return

    try:
        out = check_output([exec_name])
        lines = out.decode('utf-8').split('\n')
        for line in lines:
            if output:
                print(line)
            if 'FAILED' in line:
                raise Exception()
    except Exception as e:
        print('[SIMULATION] FAILED:'+test)
        print(e)


if __name__ == '__main__':
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    if env.dev_debug_mode:
        logging.basicConfig(**logging_setting)
    if len(sys.argv) > 1:
        exec_test(sys.argv[1])
