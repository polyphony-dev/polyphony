from polyphony import pure
from polyphony import testbench


def g(x):
    return x


@pure
def f(x):
    return g(x)


def pure06():
    return f(100)


@testbench
def test():
    assert 100 == pure06()


test()
