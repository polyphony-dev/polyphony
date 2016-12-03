import time

def testbench(func):
    return func

def top(func):
    return func

def verilog_format_to_python3_format(str):
    return str

def display(*args, end='\n'):
    if len(args) == 1:
        print(args[0], end=end)
    else:
        print(verilog_format_to_python3_format(args[0]) % tuple(args[1:]), end=end)

def write(*args):
    display(*args, end='')
