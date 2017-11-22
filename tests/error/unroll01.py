#Cannot unroll nested loop
from polyphony import testbench
from polyphony import unroll


def unroll01(x):
    sum = 0
    for i in unroll(range(4), 2):
        for j in range(4):
            sum += (i * j * x)
    return sum


@testbench
def test():
    unroll01(1)


test()