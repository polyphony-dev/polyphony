#Type of 'x' must be list or tuple, not int
from polyphony import testbench


def must_be_x_type01():
    x = 1
    return x[0]


@testbench
def test():
    must_be_x_type01()


test()
