from polyphony import testbench
from polyphony import pipelined


def pipe10_func(xs):
    for i in pipelined(range(len(xs) - 1), ii=-1):
        v = xs[i] + xs[i + 1]
        v >>= 1
        xs[i] = v


def pipe10():
    data = [0, 16, 32, -16, -64]
    pipe10_func(data)
    assert 8 == data[0]
    assert 24 == data[1]
    assert 8 == data[2]
    assert -40 == data[3]
    assert -64 == data[4]


@testbench
def test():
    pipe10()

test()
