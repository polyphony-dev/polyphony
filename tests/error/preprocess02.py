#An argument of @preprocess function must be constant
from polyphony import preprocess as pre
from polyphony import testbench


@pre
def ff(x):
    return sum([i for i in range(x)])


def f(x):
    return ff(x)


@testbench
def test():
    assert 4950 == f(100)


test()
