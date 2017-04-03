#Type of 'i' must be int, not str
from polyphony import testbench


def must_be_x_type05(i):
    x = [0]
    return x[i]


@testbench
def test():
    must_be_x_type05('0')


test()
