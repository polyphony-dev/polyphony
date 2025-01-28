from polyphony import testbench
from polyphony import pipelined


def for05(x):
    z = 0
    for i in pipelined(range(x)):
        if i > 5:
            z += 1
        else:
            z += 2
    return z


@testbench
def test():
    assert 0 == for05(0)
    assert 10 == for05(5)
    assert 16 == for05(10)
