from polyphony import testbench
from polyphony import pipelined


def loop(xs, ys, a, b, c):
    for i in pipelined(range(len(xs))):
        x = xs[i]
        x += a
        x -= b
        x *= c
        ys[i] = x


def pipe02(xs, ys, a, b, c):
    loop(xs, ys, a, b, c)      


@testbench
def test():
    data = [1, 2, 3, 4]
    out_data = [0] * 4
    pipe02(data, out_data, 1, 2, 3)
    assert 0 == out_data[0]
    assert 3 == out_data[1]
    assert 6 == out_data[2]
    assert 9 == out_data[3]


test()
