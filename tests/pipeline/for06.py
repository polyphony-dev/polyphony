from polyphony import testbench
from polyphony import pipelined


def pipe06(xs, ys):
    for i in pipelined(range(len(xs))):
        v = xs[i]
        if v < 0:
            z = (v - 8) >> 4
        else:
            z = (v + 8) >> 4
        ys[i] = z


@testbench
def test():
    data = [0, 16, 32, -16, -64]
    out = [0] * 5
    pipe06(data, out)
    assert 0 == out[0]
    assert 1 == out[1]
    assert 2 == out[2]
    assert -2 == out[3]
    assert -5 == out[4]


test()
