from polyphony import testbench
from polyphony import pipelined


def pipe13_func(xs0, xs1, xs2, xs3, ys0, ys1):
    for i in pipelined(range(len(xs0))):
        if i % 2 == 0:
            if i % 4 == 0:
                v = xs0[i]
            else:
                v = 100
        else:
            v = xs1[i]
        ys0[i] = v

        if i % 3 == 0:
            if i % 6 == 0:
                w = xs2[i]
            else:
                w = 200
        else:
            w = xs3[i]
        ys1[i] = w


def pipe13():
    idata0 = [0, 16, 32, -16, -64]
    idata1 = [32, -16, -64, 8, 24]
    idata2 = [0, 16, 32, -16, -64]
    idata3 = [32, -16, -64, 8, 24]
    odata0 = [0] * 5
    odata1 = [0] * 5
    pipe13_func(idata0, idata1, idata2, idata3, odata0, odata1)
    assert 0 == odata0[0]
    assert -16 == odata0[1]
    assert 100 == odata0[2]
    assert 8 == odata0[3]
    assert -64 == odata0[4]

    assert 0 == odata1[0]
    assert -16 == odata1[1]
    assert -64 == odata1[2]
    assert 200 == odata1[3]
    assert 24 == odata1[4]


@testbench
def test():
    pipe13()

test()
