from polyphony import testbench
from polyphony import pipelined


def pipe14_func(xs0, ys0, ys1):
    for i in pipelined(range(len(xs0))):
        v = xs0[i]
        if i % 2 == 0:
            ys0[i] = v
            ys1[i] = -v
        else:
            ys0[i] = -v
            ys1[i] = v


def pipe14():
    idata0 = [1, 16, 32, -16, -64]
    odata0 = [0] * 5
    odata1 = [0] * 5
    pipe14_func(idata0, odata0, odata1)
    assert 1 == odata0[0]
    assert -16 == odata0[1]
    assert 32 == odata0[2]
    assert 16 == odata0[3]
    assert -64 == odata0[4]

    assert -1 == odata1[0]
    assert 16 == odata1[1]
    assert -32 == odata1[2]
    assert -16 == odata1[3]
    assert 64 == odata1[4]


@testbench
def test():
    pipe14()

test()
