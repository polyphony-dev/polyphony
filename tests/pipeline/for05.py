from polyphony import testbench
from polyphony import pipelined


def pipe05(x):
    z = 0
    for i in pipelined(range(x)):
        if i > 5:
            z += 1
        else:
            z += 2
    return z


@testbench
def test():
    assert 0 == pipe05(0)
    assert 10 == pipe05(5)
    assert 16 == pipe05(10)


test()
