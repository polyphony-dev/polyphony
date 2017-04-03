#'x' is not subscriptable
from polyphony import testbench


def is_not_subscriptable01():
    x = 0
    return x[0]


@testbench
def test():
    is_not_subscriptable01()


test()
