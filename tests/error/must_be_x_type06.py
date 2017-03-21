#Type of 'i' must be int, not str
from polyphony import testbench


def must_be_x_type06(i):
    x = [0]
    x[i] = 0


@testbench
def test():
    must_be_x_type06('0')


test()
