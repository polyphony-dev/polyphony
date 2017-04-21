from polyphony import pure
from polyphony import testbench


@pure
def f(xs):
    return sum(xs)


def pure11():
    a = (1, 3, 5)
    b = (2, 4, 6)
    a_sum, b_sum  = f(a), f(b)

    return a_sum + b_sum


@testbench
def test():
    assert 21 == pure11()
    assert 21 == pure11()
    assert 21 == pure11()

test()
