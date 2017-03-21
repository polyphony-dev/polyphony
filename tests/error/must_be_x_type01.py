#Type of 'i' must be int, not str
from polyphony import testbench


def must_be_x_type01():
    x = [0]
    i = '0'
    return x[i]


@testbench
def test():
    must_be_x_type01()


test()
