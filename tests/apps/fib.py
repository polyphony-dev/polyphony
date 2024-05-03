from polyphony import testbench

def fib(n):
    a, b = 0, 1
    while a < n:
        print(a)
        a, b = b, a+b
    return

@testbench
def test():
    fib(1000)
