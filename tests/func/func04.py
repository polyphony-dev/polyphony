from polyphony import testbench

def func04(x):
    def g(a):
        return a*a

    def f(a):
        return g(a)+g(a+1)

    #TODO: post declaration
    #def g(a):
    #    return a*a

    return f(x)

@testbench
def test():
    assert 1 == func04(0)
    assert 5 == func04(1)
    assert 13 == func04(2)

test()
