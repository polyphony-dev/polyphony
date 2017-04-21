from polyphony import pure
from polyphony import testbench


@pure
def f(xs):
    return sum(xs)


@pure
def ff(xs):
    return f(xs)


def pure12():
    a = (1, 3, 5)
    a0_sum = ff(a)

    a = (2, 4, 6)
    a1_sum = ff(a)

    return a0_sum + a1_sum


@testbench
def test():
    assert 21 == pure12()


test()
