from polyphony import preprocess as pre
from polyphony import testbench


def g(x):
    return x


@pre
def f(x):
    return g(x)


def preprocess06():
    return f(100)


@testbench
def test():
    assert 100 == preprocess06()


test()
