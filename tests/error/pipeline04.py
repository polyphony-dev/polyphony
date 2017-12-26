#Cannot pipelining the loop that has an inner loop
from polyphony import testbench
from polyphony import pipelined


def pipeline04():
    s = 0
    for i in pipelined(range(10)):
        for j in range(10):
            s += i + j
    return s


@testbench
def test():
    pipeline04()


test()
