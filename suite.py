#!/usr/bin/env python3
import argparse
import sys
import os
import glob
import simu
import error
import json
from pprint import pprint


ROOT_DIR = './'
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
    'timed',
    'io',
    'channel',
    'module',
    'unroll',
    'pipeline',
    'issues',
    'pure',
)


FILES = (
    '/apps/ad7091r.py',
    '/apps/fib.py',
    '/apps/fifo.py',
    # '/apps/filter_tester.py',
    '/apps/fir.py',
    '/apps/minivm.py',
    '/apps/minivm2.py',
    '/apps/odd_even_sort.py',
    '/apps/shellsort.py',
    '/apps/stack.py',
    '/chstone/mips/mips.py',
    '/chstone/mips/pipelined_mips.py',
    '/chstone/jpeg/chenidct.py',
)


SUITE_CASES = [
    {
        'config': '{ "perfect_inlining": false }',
        "ignores": (
            'pure/*',
            'module/*',
            'typing/typing02.py', 'typing/typing03.py', 'typing/typing04.py', 'typing/typing05.py',
            'if/if22.py', 'loop/for14.py', 'return/noreturn01.py',
            'list/list16.py', 'list/list26.py', 'list/list28.py', 'list/list29.py', 'list/list30.py',
            'list/list31.py', 'list/list32.py', 'list/list33.py', 'list/list34.py',
            'list/rom04.py', 'list/rom07.py', 'list/rom08.py', 'list/rom09.py',
            'tuple/tuple12.py', 'tuple/tuple13.py', 'func/func11.py',
            'testbench/tb04.py', 'testbench/tb05.py', 'testbench/tb11.py',
            'unroll/pipelined_unroll01.py', 'unroll/unroll01.py', 'unroll/unroll02.py',
            'unroll/unroll04.py', 'unroll/unroll05.py', 'unroll/unroll06.py', 'unroll/unroll07.py',
            'unroll/unroll08.py', 'unroll/unroll09.py', 'unroll/unroll10.py', 'unroll/unroll11.py',
            'unroll/unroll12.py',
            'pipeline/for01.py', 'pipeline/for02.py', 'pipeline/for03.py', 'pipeline/for04.py',
            'pipeline/for06.py', 'pipeline/for07.py', 'pipeline/for08.py', 'pipeline/for09.py',
            'pipeline/for10.py', 'pipeline/for11.py', 'pipeline/for12.py', 'pipeline/for13.py',
            'pipeline/for14.py', 'pipeline/for15.py', 'pipeline/for16.py', 'pipeline/for17.py',
            'pipeline/for18.py', 'pipeline/nested01.py',
            'issues/cfg07.py',
            'apps/odd_even_sort.py', 'apps/shellsort.py',
            'chstone/mips/mips.py',
            'chstone/mips/pipelined_mips.py',
            'chstone/jpeg/chenidct.py',
            'error/pure01.py', 'error/pure02.py',
            'error/module_method01.py',
            'warning/pipeline_resource01.py', 'warning/pipeline_resource02.py',
        )
    },
    {
        'config': '{ "perfect_inlining": true }',
        "ignores": (
            'pure/*',
            'module/*',
            'chstone/mips/pipelined_mips.py',
            'error/pure01.py', 'error/pure02.py',
            'error/list_multiplier.py',
            'error/module_method01.py',
            'error/return_type01.py', 'error/return_type02.py',
            'error/seq_capacity02.py',
            'error/unroll02.py',
            'warning/pipeline_hazard01.py',
            'warning/pipeline_resource01.py', 'warning/pipeline_resource02.py',
        )
    },
    #{
    #    'config': '{ "enable_pure": true, \
    #                 "internal_ram_threshold_size": 0, \
    #                 "default_int_width": 32 }',
    #    "ignores": ('error/io_conflict02.py',)
    #},
]

default_ignores = []
global_suite_results = []


def parse_options():
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    parser = argparse.ArgumentParser(prog='suite')
    parser.add_argument('-c', dest='compile_only', action='store_true')
    parser.add_argument('-e', dest='error_test_only', action='store_true')
    parser.add_argument('-w', dest='warn_test_only', action='store_true')
    parser.add_argument('-j', dest='show_json', action='store_true')
    parser.add_argument('-s', dest='silent', action='store_true')
    parser.add_argument('-f', dest='full', action='store_true')
    parser.add_argument('dir', nargs='*')
    return parser.parse_args()


def add_files(lst, patterns):
    for p in patterns:
        for f in glob.glob('{0}/{1}'.format(TEST_DIR, p)):
            f = f.replace('\\', '/')
            lst.append(f)


def suite(options, ignores):
    tests = []
    suite_results = {}
    ds = options.dir if options.dir else DIRS
    for d in ds:
        fs = glob.glob('{0}/{1}/*.py'.format(TEST_DIR, d))
        fs = [f.replace('\\', '/') for f in fs]
        tests.extend(sorted(fs))
    if not options.dir:
        tests.extend([TEST_DIR + f for f in FILES])
    for t in ignores:
        if t in tests:
            tests.remove(t)
    fails = 0
    for t in tests:
        if not options.silent:
            print(t)
        finishes = simu.exec_test(t, options)
        if finishes:
            suite_results[t] = ','.join(finishes)
        else:
            suite_results[t] = 'FAIL'
            fails += 1
    if options.config:
        suite_results['-config'] = json.loads(options.config)
    global_suite_results.append(suite_results)
    return fails


def error_test(options, ignores):
    return abnormal_test(options, ignores, True)


def warn_test(options, ignores):
    return abnormal_test(options, ignores, False)


def abnormal_test(options, ignores, is_err):
    if is_err:
        tests = sorted(glob.glob('{0}/error/*.py'.format(TEST_DIR)))
        proc = error.error_test
    else:
        tests = sorted(glob.glob('{0}/warning/*.py'.format(TEST_DIR)))
        proc = error.warn_test
    for t in ignores:
        if t in tests:
            tests.remove(t)
    fails = 0
    for t in tests:
        if not options.silent:
            print(t)
        if not proc(t, options):
            fails += 1
    return fails


def suite_main():
    options = parse_options()
    options.debug_mode = False
    options.verilog_dump = False
    options.verilog_monitor = False
    if os.path.exists('.suite_ignores'):
        with open('.suite_ignores', 'r') as f:
            default_ignores.extend(f.read().splitlines())
    if options.compile_only or options.dir:
        procs = (suite,)
    elif options.error_test_only:
        procs = (error_test,)
    elif options.warn_test_only:
        procs = (warn_test,)
    else:
        procs = (suite, error_test, warn_test)

    fails = 0
    if options.full:
        for case in SUITE_CASES:
            ignores = []
            add_files(ignores, default_ignores)
            if not options.silent:
                pprint(case)
            add_files(ignores, case['ignores'])
            if ignores and not options.silent:
                print('NOTE: these files will be ignored')
                print(ignores)
            options.config = case['config']
            results = [p(options, ignores) for p in procs]
            fails += sum(results)
    else:
        ignores = []
        add_files(ignores, default_ignores)
        if ignores and not options.silent:
            print('NOTE: these files will be ignored')
            print(ignores)
        options.config = None
        results = [p(options, ignores) for p in procs]
        fails += sum(results)

    json_result = json.dumps(global_suite_results, sort_keys=True, indent=4)
    with open('suite.json', 'w') as f:
        f.write(json_result)
    if options.show_json:
        print(json_result)
    return fails


if __name__ == '__main__':
    ret = suite_main()
    sys.exit(ret)
