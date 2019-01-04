from polyphony import testbench
from polyphony import pipelined


def nested06(x):
    s = x
    for i in pipelined(range(4)):
        t = i
        for j in range(4):
            t += 1
            for k in range(4):
                s += 2
                for l in range(4):
                    s += 3
        s += t
    return s


@testbench
def test():
    assert 928 == nested06(10)


test()
