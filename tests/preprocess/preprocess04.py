from polyphony import preprocess as pre
from polyphony import testbench


@pre
def f(x):
    return x


@pre
def g(x):
    return x


@pre
def h(x):
    return x


def preprocess04():
    return f(g(h(100)))


@testbench
def test():
    assert 100 == preprocess04()


test()
