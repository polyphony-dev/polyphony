from polyphony import testbench
from polyphony import pipelined


def pipe16_func(xs0, xs1, ys0, ys1):
    for i in pipelined(range(len(ys0))):
        if i % 3 == 0:
            ys0[i] = xs0[0] * xs1[1]
            ys1[i] = xs1[0] * xs0[1]
        elif i % 3 == 1:
            ys0[i] = xs0[1] * xs1[2]
            ys1[i] = xs1[1] * xs0[2]
        else:
            ys0[i] = xs0[2] * xs1[3]
            ys1[i] = xs1[2] * xs0[3]


def pipe16():
    idata0 = [1, 2, 3, 4]
    idata1 = [2, 3, 4, 5]
    odata0 = [0] * 5
    odata1 = [0] * 5
    pipe16_func(idata0, idata1, odata0, odata1)
    assert 3 == odata0[0]
    assert 8 == odata0[1]
    assert 15 == odata0[2]
    assert 3 == odata0[3]
    assert 8 == odata0[4]

    assert 4 == odata1[0]
    assert 9 == odata1[1]
    assert 16 == odata1[2]
    assert 4 == odata1[3]
    assert 9 == odata1[4]


@testbench
def test():
    pipe16()

test()
