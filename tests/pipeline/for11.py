from polyphony import testbench
from polyphony import pipelined


def pipe11_func(xs, ys):
    for i in pipelined(range(len(xs) - 1), ii=2):
        v = xs[i] + xs[i + 1]
        v >>= 1
        ys[i] = v


def pipe11():
    idata = [0, 16, 32, -16, -64]
    odata = [0] * 5
    pipe11_func(idata, odata)
    assert 8 == odata[0]
    assert 24 == odata[1]
    assert 8 == odata[2]
    assert -40 == odata[3]
    assert 0 == odata[4]


@testbench
def test():
    pipe11()

test()
