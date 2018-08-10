from polyphony import testbench
from polyphony import pipelined


def pipe09(xs, w):
    for i in pipelined(range(len(xs))):
        v = xs[i]
        v *= w
        xs[i] = v


@testbench
def test():
    data = [0, 16, 32, -16, -64]
    pipe09(data, 2)
    assert 0 == data[0]
    assert 32 == data[1]
    assert 64 == data[2]
    assert -32 == data[3]
    assert -128 == data[4]


test()
