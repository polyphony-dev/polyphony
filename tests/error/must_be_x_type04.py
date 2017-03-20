#Type of 'y' must be int, not list
from polyphony import testbench


def must_be_x_type03():
    x = [0]
    y = [0]
    x[y] = 0


@testbench
def test():
    must_be_x_type03()


test()
