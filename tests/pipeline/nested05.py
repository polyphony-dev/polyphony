from polyphony import testbench
from polyphony import pipelined


def nested05(x):
    s = x
    for i in pipelined(range(4)):
        t = i
        for j in range(4):
            s += 1
            for k in range(4):
                t += 1
        s += t
    return s


@testbench
def test():
    assert 96 == nested05(10)
