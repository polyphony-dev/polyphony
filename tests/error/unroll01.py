#Cannot unroll nested loop
from polyphony import testbench
from polyphony import rule


def unroll01(x):
    sum = 0
    with rule(unroll='2'):
        for i in range(4):
            with rule(unroll='1'):
                for j in range(4):
                    sum += (i * j * x)
    return sum


@testbench
def test():
    unroll01(1)


test()