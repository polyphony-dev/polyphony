from polyphony import testbench
from polyphony import pipelined


def pipe_func(a, b, c):
    for i in range(8):
        s = 0
        for k in pipelined(range(8)):
            s += a[k] * b[i]
        c[i] = s
    print(c[0], c[1], c[2], c[3])


def pipe04():
    data_a = [1, 3, 5, 7, 5, 3, 1, 0]
    data_b = [1, -1, 2, -2, 3, -3, 4, -5]
    data_c = [None] * 8
    pipe_func(data_a, data_b, data_c)
    assert 25 == data_c[0]
    assert -25 == data_c[1]
    assert 50 == data_c[2]
    assert -50 == data_c[3]


@testbench
def test():
    pipe04()

test()
