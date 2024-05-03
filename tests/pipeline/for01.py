from polyphony import testbench
from polyphony import pipelined


def pipe_func(xs, ys, a, b, c):
    for i in pipelined(range(len(xs))):
        x = xs[i]
        x += a
        x -= b
        x *= c
        print(x)
        ys[i] = x

def for01(a, b, c):
    data = [1, 2, 3, 4]
    out_data = [0] * 4
    pipe_func(data, out_data, a, b, c)
    assert 0 == out_data[0]
    assert 3 == out_data[1]
    assert 6 == out_data[2]
    assert 9 == out_data[3]


@testbench
def test():
    for01(1, 2, 3)
