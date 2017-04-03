#Type of sequence multiplier must be constant
from polyphony import testbench


def list_multiplier(x):
    l = [1, 2, 3] * x
    return l[0]


@testbench
def test():
    list_multiplier(5)


test()