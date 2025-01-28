from polyphony import testbench
from polyphony import pipelined


def nested02(x):
    s = x
    for i in pipelined(range(4)):
        for j in range(4):
            s += 1
    return s


@testbench
def test():
    assert 26 == nested02(10)
