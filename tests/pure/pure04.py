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
    return f(g(h(100)))


@testbench
def test():
    assert 100 == pure04()


test()
