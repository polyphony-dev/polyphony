#Cannot pipelining the loop that has an inner loop
from polyphony import testbench
from polyphony import rule


def pipeline04():
    s = 0
    with rule(scheduling='pipeline'):
        for i in range(10):
            for j in range(10):
                s += i + j
    return s


@testbench
def test():
    pipeline04()


test()
