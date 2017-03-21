#'x' is not subscriptable
from polyphony import testbench


def is_not_subscriptable02():
    x = 0
    x[0] = 0


@testbench
def test():
    is_not_subscriptable02()


test()
