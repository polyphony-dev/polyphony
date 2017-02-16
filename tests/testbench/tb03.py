from polyphony import testbench

def g(x):
    return x

def f(x):
    return g(x) + g(x)

@testbench
def test():
    a = 10
    assert a+a == f(a)
    b = f(1) + f(1)
    assert b == f(2)

test()
