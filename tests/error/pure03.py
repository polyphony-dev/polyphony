#An argument of @pure function must be constant
from polyphony import pure
from polyphony import testbench


@pure
def f(xs):
    return sum(xs)


def ff(xs):
    return f(xs)


def pure03():
    return ff((1, 3, 5))


@testbench
def test():
    pure03()


test()
