#Unsupported expression
from polyphony import testbench


def unsupported_expr03(a):
    l = [0]
    return l[[a]]


@testbench
def test():
    unsupported_expr03(1)


test()
