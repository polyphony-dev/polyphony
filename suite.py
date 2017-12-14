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
    'unroll',
    'pure',
)

FILES = (
    TEST_DIR + '/apps/ad7091r.py',
    TEST_DIR + '/apps/fib.py',
    TEST_DIR + '/apps/fifo.py',
    TEST_DIR + '/apps/fir.py',
    TEST_DIR + '/apps/minivm.py',
    TEST_DIR + '/apps/minivm2.py',
    TEST_DIR + '/apps/odd_even_sort.py',
    TEST_DIR + '/apps/shellsort.py',
    TEST_DIR + '/apps/stack.py',
    TEST_DIR + '/chstone/mips/mips.py',
    TEST_DIR + '/chstone/jpeg/chenidct.py',
)


def suite(compile_only, *cases):
    suite_results = {}
    tests = []
    if cases[0]:
        ds = cases
    else:
        ds = DIRS
    for d in ds:
        tests.extend(sorted(glob.glob('{1}{0}{2}{0}*.py'.format(os.path.sep, TEST_DIR, d))))
    if not cases[0]:
        tests.extend(FILES)
    for t in tests:
        print(t)
        finishes = simu.exec_test(t, output=False, compile_only=compile_only)
        if finishes:
            suite_results[t] = ','.join(finishes)
        else:
            suite_results[t] = 'FAIL'
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
