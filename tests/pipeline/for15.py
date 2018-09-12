from polyphony import testbench
from polyphony import pipelined


def pipe15(xs0, xs1, ys0, ys1):
    for i in pipelined(range(len(ys0)), ii=1):
        if i == 0:
            ys0[i] = xs0[0]
        else:
            ys0[i] = 1


@testbench
def test():
    idata0 = [10, 2, 3, 4]
    idata1 = [2, 3, 4, 5]
    odata0 = [0] * 5
    odata1 = [0] * 5
    pipe15(idata0, idata1, odata0, odata1)
    print(odata0[0], odata0[1], odata0[2])
    assert 10 == odata0[0]
    assert 1 == odata0[1]
    assert 1 == odata0[2]
    assert 1 == odata0[3]
    assert 1 == odata0[4]

    #assert 4 == odata1[0]
    #assert 3 == odata1[1]
    #assert 20 == odata1[2]
    #assert 4 == odata1[3]
    #assert 3 == odata1[4]

test()
