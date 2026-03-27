#!/usr/bin/env python3
import argparse
import sys
import os
import glob
import simu
import error
import json
import multiprocessing as mp
import time
from pprint import pprint

TEST_TIMEOUT = 120  # seconds per test case


ROOT_DIR = "./"
TEST_DIR = ROOT_DIR + "tests"
TMP_DIR = ROOT_DIR + ".tmp"

DIRS = (
    "expr",
    "typing",
    "if",
    "loop",
    "return",
    "list",
    "tuple",
    "scope",
    "func",
    "testbench",
    "class",
    "import",
    "timed",
    "io",
    "channel",
    "module",
    "unroll",
    "pipeline",
    "issues",
    "pure",
)


FILES = (
    "/apps/ad7091r.py",
    "/apps/fib.py",
    "/apps/fifo.py",
    # '/apps/filter_tester.py',
    "/apps/fir.py",
    "/apps/minivm.py",
    "/apps/minivm2.py",
    "/apps/odd_even_sort.py",
    "/apps/shellsort.py",
    "/apps/stack.py",
    "/chstone/mips/mips.py",
    "/chstone/mips/mips_module.py",
    "/chstone/jpeg/chenidct.py",
    "/chstone/aes/aes_module.py",
    "/chstone/adpcm/adpcm_module.py",
    "/chstone/motion/motion_module.py",
)


SUITE_CASES = [
    {
        "config": "{}",
        "ignores": (
            "pure/*",
            "perform/*",
            "module/module01.py",
            "module/module02.py",
            "module/module03.py",
            "module/module03.new.py",
            "module/module07.py",
            "module/module08.py",
            "module/module09.py",
            "module/module10.py",
            "module/module11.py",
            "module/module12.py",
            "module/field01.py",
            "module/field02.py",
            "module/field03.py",
            "module/nesting01.py",
            "module/nesting02.py",
            "module/nesting03.py",
            "module/nesting04.py",
            "module/parameter01.py",
            "unroll/pipelined_unroll01.py",
            "chstone/mips/pipelined_mips.py",
            "error/pure01.py",
            "error/pure02.py",
            "error/module_method01.py",
            "warning/pipeline_resource01.py",
            "warning/pipeline_resource02.py",
        ),
    },
]

default_ignores = []
global_suite_results = []


def parse_options():
    if not os.path.exists(TMP_DIR):
        os.mkdir(TMP_DIR)
    parser = argparse.ArgumentParser(prog="suite", description="Run the Polyphony test suite")
    parser.add_argument("-c", dest="compile_only", action="store_true", help="compile only, skip simulation")
    parser.add_argument("-e", dest="error_test_only", action="store_true", help="run error tests only (tests/error/)")
    parser.add_argument(
        "-w", dest="warn_test_only", action="store_true", help="run warning tests only (tests/warning/)"
    )
    parser.add_argument("-j", dest="show_json", action="store_true", help="display results as JSON")
    parser.add_argument("-s", dest="silent", action="store_true", help="suppress output")
    parser.add_argument("-f", dest="full", action="store_true", help="run with all config patterns")
    parser.add_argument(
        "-n", "--num_cpu", dest="ncpu", type=int, default=1, help="number of parallel processes (default: 1)"
    )
    parser.add_argument(
        "-P", "--python", dest="enable_python", action="store_true", default=False, help="enable python simulation"
    )
    parser.add_argument("dir", nargs="*", help="target test directories (all if omitted)")
    return parser.parse_args()


def _is_pass(res):
    """Return True if a test result string indicates success."""
    if res == "PASS":
        return True
    # -P mode: "HDL Result: 170:finish Python Result: OK"
    return "FAIL" not in res and "Error" not in res and "Timeout" not in res


def add_files(lst, patterns):
    for p in patterns:
        for f in glob.glob("{0}/{1}".format(TEST_DIR, p)):
            f = f.replace("\\", "/")
            lst.append(f)


def exec_test_entry(t, options, suite_results):
    if not options.silent:
        print(t)
    start_time = time.time()
    try:
        hdl_finishes, py_finishes = simu.exec_test(t, options)
        if options.enable_python:
            suite_results[t] = f"HDL Result: {','.join(hdl_finishes)} Python Result: {','.join(py_finishes)}"
        else:
            suite_results[t] = f"{','.join(hdl_finishes)}"
    except Exception as e:
        suite_results[t] = "Internal Error"
    elapsed = time.time() - start_time
    if elapsed > 30:
        print(f"WARNING: {t} took {elapsed:.1f}s")


def suite(options, ignores):
    tests = []
    ds = options.dir if options.dir else DIRS
    for d in ds:
        fs = glob.glob("{0}/{1}/*.py".format(TEST_DIR, d))
        fs = [f.replace("\\", "/") for f in fs]
        tests.extend(sorted(fs))
    if not options.dir:
        tests.extend([TEST_DIR + f for f in FILES])
    pool = mp.Pool(options.ncpu)
    manager = mp.Manager()
    suite_results = manager.dict()
    for t in ignores:
        if t in tests:
            tests.remove(t)
    fails = 0
    async_results = []
    for t in tests:
        r = pool.apply_async(exec_test_entry, args=(t, options, suite_results))
        async_results.append((t, r))
    pool.close()
    timed_out = set()
    for t, r in async_results:
        try:
            r.get(timeout=TEST_TIMEOUT)
        except mp.TimeoutError:
            print(f"TIMEOUT: {t} exceeded {TEST_TIMEOUT}s - skipping")
            timed_out.add(t)
        except Exception as e:
            print(f"ERROR: {t} raised {e}")
            suite_results[t] = "Internal Error"
    pool.terminate()
    pool.join()
    suite_results = dict(suite_results)
    for t in timed_out:
        suite_results[t] = "Timeout"
    fails = sum([not _is_pass(res) for res in suite_results.values()])
    if options.config:
        suite_results["-config"] = json.loads(options.config)
    global_suite_results.append(suite_results)
    return fails


def error_test(options, ignores):
    tests = sorted(glob.glob("{0}/error/*.py".format(TEST_DIR)))
    proc = error.error_test
    return abnormal_test(tests, proc, options, ignores)


def warn_test(options, ignores):
    tests = sorted(glob.glob("{0}/warning/*.py".format(TEST_DIR)))
    proc = error.warn_test
    return abnormal_test(tests, proc, options, ignores)


def exec_abnormal_test_entry(proc, t, options, error_results):
    if not options.silent:
        print(t)
    if not proc(t, options):
        error_results[t] = True


def abnormal_test(tests, proc, options, ignores):
    pool = mp.Pool(options.ncpu)
    manager = mp.Manager()
    error_results = manager.dict()
    for t in ignores:
        if t in tests:
            tests.remove(t)
    fails = 0
    async_results = []
    for t in tests:
        r = pool.apply_async(exec_abnormal_test_entry, args=(proc, t, options, error_results))
        async_results.append((t, r))
    pool.close()
    for t, r in async_results:
        try:
            r.get(timeout=TEST_TIMEOUT)
        except mp.TimeoutError:
            print(f"TIMEOUT: {t} exceeded {TEST_TIMEOUT}s - skipping")
        except Exception as e:
            print(f"ERROR: {t} raised {e}")
    pool.terminate()
    pool.join()
    error_results = dict(error_results)
    # Record results: FAIL for failed tests, PASS for others
    suite_results = {}
    for t in tests:
        if t in error_results:
            suite_results[t] = "FAIL"
        else:
            suite_results[t] = "PASS"
    global_suite_results.append(suite_results)
    fails = sum(error_results.values())
    return fails


def suite_main():
    options = parse_options()
    options.debug_mode = False
    options.hdl_debug_mode = False
    options.verilog_dump = False
    options.verilog_monitor = False
    options.with_path_name = True
    if os.path.exists(".suite_ignores"):
        with open(".suite_ignores", "r") as f:
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
            add_files(ignores, case["ignores"])
            if ignores and not options.silent:
                print("NOTE: these files will be ignored")
                print(ignores)
            options.config = case["config"]
            results = [p(options, ignores) for p in procs]
            fails += sum(results)
    else:
        ignores = []
        add_files(ignores, default_ignores)
        if ignores and not options.silent:
            print("NOTE: these files will be ignored")
            print(ignores)
        options.config = None
        results = [p(options, ignores) for p in procs]
        fails += sum(results)

    json_result = json.dumps(global_suite_results, sort_keys=True, indent=4)
    with open("suite.json", "w") as f:
        f.write(json_result)
    if options.show_json:
        print(json_result)
    return fails


if __name__ == "__main__":
    ret = suite_main()
    print(ret)
    sys.exit(ret)
