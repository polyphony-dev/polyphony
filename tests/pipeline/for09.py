from polyphony import testbench
from polyphony import pipelined


def pipe_func(xs, w):
    for i in pipelined(range(len(xs))):
        v = xs[i]
        v *= w
        xs[i] = v


def pipe09():
    data = [1, 16, 32, -16, -64]
    pipe_func(data, 2)
    print(data[0])
    print(data[1])
    print(data[2])
    print(data[3])
    print(data[4])
    assert 2 == data[0]
    assert 32 == data[1]
    assert 64 == data[2]
    assert -32 == data[3]
    assert -128 == data[4]


@testbench
def test():
    pipe09()

test()
