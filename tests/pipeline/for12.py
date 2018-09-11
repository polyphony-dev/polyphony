from polyphony import testbench
from polyphony import pipelined


def pipe12(xs0, xs1, ys0):
    for i in pipelined(range(len(xs0))):
        if i % 2 == 0:
            v = xs0[i]
        else:
            v = xs1[i]
        #print(i, v, xs0[i], xs1[i])
        ys0[i] = v


@testbench
def test():
    idata0 = [0, 16, 32, -16, -64]
    idata1 = [32, -16, -64, 8, 24]
    odata0 = [0] * 5
    pipe12(idata0, idata1, odata0)
    assert 0 == odata0[0]
    assert -16 == odata0[1]
    assert 32 == odata0[2]
    assert 8 == odata0[3]
    assert -64 == odata0[4]


test()
