#!/usr/bin/env python3

import sys
import os
import glob
import simu
import error
import json

ROOT_DIR = '.' + os.path.sep
TEST_DIR = ROOT_DIR + 'tests'
TMP_DIR  = ROOT_DIR + '.tmp'

DIRS = (
    'expr',
    'typing',
    'if',
    'loop',
    'return',
    'list',
    'tuple',
    'scope',
    'func',
    'testbench',
    'class',
    'import',
    'io',
    'module',
    'pure',
)


def suite(compile_only, *cases):
    suite_results = {}
    if cases[0]:
        ds = cases
    else:
        ds = DIRS
    for d in ds:
        suite_cases = {}
        suite_results[d] = suite_cases
        for t in sorted(glob.glob('{1}{0}{2}{0}*.py'.format(os.path.sep, TEST_DIR, d))):
            print(t)
            finishes = simu.exec_test(t, output=False, compile_only=compile_only)
            filename = os.path.basename(t)
            if finishes:
                suite_cases[filename] = ','.join(finishes)
            else:
                suite_cases[filename] = 'FAIL'
    with open('suite.json', 'w') as f:
        f.write(json.dumps(suite_results, sort_keys=True, indent=4))


def error_test():
    for t in sorted(glob.glob('{1}{0}error{0}*.py'.format(os.path.sep, TEST_DIR))):
        print(t)
        error.error_test(t, output=False)


def suite_main():
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)

    compile_only = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'c':
            compile_only = True
            if len(sys.argv) > 2:
                suite(compile_only, *sys.argv[2:])
            else:
                suite(compile_only, None)
        elif sys.argv[1] == 'e':
            error_test()
        else:
            suite(compile_only, *sys.argv[1:])
    else:
        suite(False, None)
        error_test()


if __name__ == '__main__':
    suite_main()
