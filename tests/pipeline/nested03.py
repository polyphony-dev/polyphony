from polyphony import testbench
from polyphony import pipelined


def nested03(x):
    s = x
    for i in pipelined(range(4)):
        t = i
        s += i
        for j in range(4):
            s += 1
            t += 1
        t += 2
        s += t
    return s


@testbench
def test():
    assert 62 == nested03(10)


test()
