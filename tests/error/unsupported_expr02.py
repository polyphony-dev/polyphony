#Unsupported expression
from polyphony import testbench


def unsupported_expr02(a):
    return [0] + a


@testbench
def test():
    unsupported_expr02(1)


test()
