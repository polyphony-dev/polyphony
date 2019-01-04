#Flattening of multiple inner loops in a pipeline loop is not supported
from polyphony import testbench
from polyphony import pipelined


def pipeline04():
    s = 0
    for i in pipelined(range(10)):
        for j in range(10):
            s += i + j
        for j in range(12):
            s += i + j
    return s


@testbench
def test():
    pipeline04()


test()
