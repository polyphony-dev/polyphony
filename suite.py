#!/usr/bin/env python3

import sys
import os
import glob
import simu
import error

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
    if cases[0]:
        ds = cases
    else:
        ds = DIRS
    for d in ds:
        for t in sorted(glob.glob('{1}{0}{2}{0}*.py'.format(os.path.sep, TEST_DIR, d))):
            print(t)
            simu.exec_test(t, output=False, compile_only=compile_only)


def error_test():
    for t in sorted(glob.glob('{1}{0}error{0}*.py'.format(os.path.sep, TEST_DIR))):
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
