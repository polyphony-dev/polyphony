#!/usr/bin/env python3

import sys
import os
import glob

ROOT_DIR = './'
TEST_DIR = ROOT_DIR+'tests'
TMP_DIR  = ROOT_DIR+'.tmp'

import simu

DIRS = (
    'expr',
    'if',
    'loop',
    'return',
    'list',
    'tuple',
    'scope',
    'func',
    'parallel',
    'testbench',
    'class',
)


def suite(compile_only, *cases):
    if cases[0]:
        ds = cases
    else:
        ds = DIRS
    for d in ds:
        for t in glob.glob('{}/{}/*.py'.format(TEST_DIR, d)):
            print(t)
            simu.exec_test(t, output=False, compile_only=compile_only)

if __name__ == '__main__':
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
        else:
            suite(compile_only, *sys.argv[1:])
    else:
        suite(False, None)
