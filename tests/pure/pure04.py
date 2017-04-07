from polyphony import pure
from polyphony import testbench


@pure
def f(x):
    return x


@pure
def g(x):
    return x


@pure
def h(x):
    return x


def pure04():
    #return f(g(h(100))) + f(10) + g(10) + h(10)
    return f(10) + f(20) + f(30)


@testbench
def test():
    assert 60 == pure04()


test()
