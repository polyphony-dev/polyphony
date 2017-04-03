#'x' is not subscriptable
from polyphony import testbench


def is_not_subscriptable03(x):
    x[1] = 0


@testbench
def test():
    is_not_subscriptable03(0)


test()
