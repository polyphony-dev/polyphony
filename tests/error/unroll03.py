#'polyphony.unroll' is incompatible type as a parameter of polyphony.unroll()
from polyphony import testbench
from polyphony import unroll


def unroll03(x):
    sum = 0
    for i in unroll(unroll(range(4))):
        sum += i
    return sum


@testbench
def test():
    unroll03(1)


test()