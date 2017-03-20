#Type of 'x' must be list or tuple, not int
from polyphony import testbench


def must_be_x_type02():
    x = 1
    x[0] = 0


@testbench
def test():
    must_be_x_type02()


test()
