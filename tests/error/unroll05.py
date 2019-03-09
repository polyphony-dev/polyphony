#The unroll factor value must be a constant
from polyphony import testbench
from polyphony import unroll


def unroll05(x, factor):
    sum = 0
    for i in unroll(range(4), factor):
        sum += i
    return sum


@testbench
def test():
    unroll05(1, 1)


test()