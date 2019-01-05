from polyphony import testbench
from polyphony import pipelined


def pipe07(xs, ys):
    for i in pipelined(range(len(xs))):
        v = xs[i]
        if v < 0:
            z = (v - 8) >> 4
        else:
            z = (v + 8) >> 4
        ys[i] = z

    for i in pipelined(range(len(ys))):
        v = ys[i]
        #print(i, v)
        if v < 0:
            z = (v - 8) << 4
        else:
            z = (v + 8) << 4
        xs[i] = z


@testbench
def test():
    data = [0, 16, 32, -16, -64]
    out = [0] * 5
    pipe07(data, out)
    assert 0 == out[0]
    assert 1 == out[1]
    assert 2 == out[2]
    assert -2 == out[3]
    assert -5 == out[4]

    assert 128 == data[0]
    assert 144 == data[1]
    assert 160 == data[2]
    assert -160 == data[3]
    assert -208 == data[4]


test()
