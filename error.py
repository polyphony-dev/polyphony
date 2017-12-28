#!/usr/bin/env python3
import argparse
import sys
import os
import traceback
import io
import types
from contextlib import redirect_stdout


ROOT_DIR = '.' + os.path.sep
TEST_DIR = ROOT_DIR + 'tests'
TMP_DIR  = ROOT_DIR + '.tmp'
sys.path.append(ROOT_DIR)

from polyphony.compiler.__main__ import compile_main, logging_setting
from polyphony.compiler.env import env


def parse_options():
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    parser = argparse.ArgumentParser(prog='simu')
    parser.add_argument('-c', '--config', dest='config',
                        metavar='CONFIG', help='set configration(json literal or file)')
    parser.add_argument('-d', '--enable_debug', dest='debug_mode',
                        action='store_true', help='enable debug mode')
    parser.add_argument('-w', dest='warn_test', action='store_true')
    parser.add_argument('source', help='Python source file')
    return parser.parse_args()


def make_compile_options(casename, err_options, quiet_level):
    options = types.SimpleNamespace()
    options.config = err_options.config
    options.output_name = casename
    options.output_dir = TMP_DIR
    options.verbose_level = 0
    options.quiet_level = quiet_level
    options.debug_mode = err_options.debug_mode
    options.verilog_dump = False
    options.verilog_monitor = False
    return options


def error_test(casefile_path, err_options):
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    with open(casefile_path, 'r') as f:
        first_line = f.readline()
        if not first_line.startswith('#'):
            print('The file is not error test file')
            sys.exit(0)
        expected_msg = first_line.split('#')[1].rstrip('\n')
    options = make_compile_options(casename, err_options, env.QUIET_ERROR)
    try:
        compile_main(casefile_path, options)
    except AssertionError:
        raise
    except Exception as e:
        if e.args[0] == expected_msg:
            return True
        if err_options.debug_mode:
            traceback.print_exc()
        print(casefile_path)
        print('[ERROR TEST] FAILED: actual "{}", expected "{}"'.format(e.args[0], expected_msg))
        return False
    print(casefile_path)
    print('[ERROR TEST] FAILED: No exception was raised')
    return False


def warn_test(casefile_path, err_options):
    casefile = os.path.basename(casefile_path)
    casename, _ = os.path.splitext(casefile)
    with open(casefile_path, 'r') as f:
        first_line = f.readline()
        if not first_line.startswith('#'):
            print('The file is not error test file')
            sys.exit(0)
        expected_msg = first_line.split('#')[1].rstrip('\n')
    f = io.StringIO()
    err_options.debug_mode = False
    options = make_compile_options(casename, err_options, 0)
    with redirect_stdout(f):
        try:
            compile_main(casefile_path, options)
        except Exception as e:
            print(casefile_path)
            print('[WARNING TEST] FAILED')
    msg = f.getvalue()
    #print(msg)
    header = 'Warning: '
    for line in msg.split('\n'):
        if line.startswith(header):
            actual_msg = line[len(header):]
            if actual_msg != expected_msg:
                print(casefile_path)
                print('[WARNING TEST] FAILED: actual "{}", expected "{}"'.format(actual_msg, expected_msg))
            return True
    print(casefile_path)
    print('[WARNING TEST] FAILED: No warning messages')
    return False


if __name__ == '__main__':
    options = parse_options()
    if not options.warn_test:
        error_test(options.source, options)
    else:
        warn_test(options.source, options)
