.. image:: https://travis-ci.org/ktok07b6/polyphony.svg?branch=devel
    :target: https://travis-ci.org/ktok07b6/polyphony
.. image:: https://badge.fury.io/py/polyphony.svg
    :target: https://badge.fury.io/py/polyphony

polyphony
=========
Polyphony is Python based High-Level Synthesis compiler.

Requirements
------------
Python 3.6 or later

Installation
------------
$ pip3 install polyphony

Usage
-----
usage: polyphony [-h] [-o FILE] [-d DIR] [-c CONFIG] [-v] [-D] [-q] [-vd]
                 [-vm] [-V]
                 source

positional arguments:
  source                Python source file

optional arguments:
  -h, --help            show this help message and exit
  -o FILE, --output FILE
                        output filename (default is "polyphony_out")
  -d DIR, --dir DIR     output directory
  -c CONFIG, --config CONFIG
                        set configration(json literal or file)
  -v, --verbose         verbose output
  -D, --debug           enable debug mode
  -q, --quiet           suppress warning/error messages
  -vd, --verilog_dump   output vcd file in testbench
  -vm, --verilog_monitor
                        enable $monitor in testbench
  -V, --version         print the Polyphony version number

Examples
--------

see https://github.com/ktok07b6/polyphony/tree/master/tests

