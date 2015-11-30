from polyphony import testbench

def func03(x):
    def f(a):
        return a
    def g(a):
        return -a

    return f(x) + f(x+1) + g(x+2) + g(x+3)

@testbench
def test():
    assert -4 == func03(0)
    assert -4 == func03(1)
    assert -4 == func03(2)

test()

