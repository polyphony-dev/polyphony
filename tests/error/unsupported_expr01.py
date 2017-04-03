#Unsupported expression
from polyphony import testbench


def unsupported_expr01(a):
    return not not a


@testbench
def test():
    unsupported_expr01(True)


test()
