#!/usr/bin/env python3
import sys
import os
import traceback
import io
from contextlib import redirect_stdout


ROOT_DIR = '.' + os.path.sep
TEST_DIR = ROOT_DIR + 'tests'
TMP_DIR  = ROOT_DIR + '.tmp'
sys.path.append(ROOT_DIR)

from polyphony.compiler.__main__ import compile_main, logging_setting
from polyphony.compiler.env import env


def error_test(casefile_path, output=True):
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    with open(casefile_path, 'r') as f:
        first_line = f.readline()
        if not first_line.startswith('#'):
            print('The file is not error test file')
            sys.exit(0)
        expected_msg = first_line.split('#')[1].rstrip('\n')
    try:
        compile_main(casefile_path, casename, TMP_DIR, debug_mode=output)
    except AssertionError:
        raise
    except Exception as e:
        if e.args[0] == expected_msg:
            return
        if env.dev_debug_mode:
            traceback.print_exc()
        print(casefile_path)
        print('[ERROR TEST] FAILED: actual "{}", expected "{}"'.format(e.args[0], expected_msg))
        return
    print(casefile_path)
    print('[ERROR TEST] FAILED: No exception was raised')


def warn_test(casefile_path, output=True):
    
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    #sys.stdout = 
    with open(casefile_path, 'r') as f:
        first_line = f.readline()
        if not first_line.startswith('#'):
            print('The file is not error test file')
            sys.exit(0)
        expected_msg = first_line.split('#')[1].rstrip('\n')
    f = io.StringIO()
    with redirect_stdout(f):
        try:
            compile_main(casefile_path, casename, TMP_DIR, debug_mode=output)
        except Exception as e:
            print(casefile_path)
            print('[WARNING TEST] FAILED')
    msg = f.getvalue()
    header = 'Warning: '
    for line in msg.split('\n'):
        if line.startswith(header):
            actual_msg = line[len(header):]
            if actual_msg != expected_msg:
                print(casefile_path)
                print('[WARNING TEST] FAILED: actual "{}", expected "{}"'.format(actual_msg, expected_msg))
            return
    print(casefile_path)
    print('[WARNING TEST] FAILED: No warning messages')


if __name__ == '__main__':
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    if len(sys.argv) > 1:
        if sys.argv[1] == 'w':
            warn_test(sys.argv[2])
        else:
            error_test(sys.argv[1])
