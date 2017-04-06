#An argument of @pure function must be constant
from polyphony import pure
from polyphony import testbench


@pure
def ff(x):
    return sum([i for i in range(x)])


def f(x):
    return ff(x)


@testbench
def test():
    assert 4950 == f(100)


test()
