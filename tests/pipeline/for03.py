from polyphony import testbench
from polyphony import pipelined


def pipe03(xs):
    s = 0
    for x in pipelined(xs):
        x = x + s
        s += x
    return s


@testbench
def test():
    data_a = [1, 1, 1, 1, 1, 1, 1, 1]
    data_b = [1, 2, 3, 4, 5, 6, 7, 8]
    assert 255 == pipe03(data_a)
    assert 502 == pipe03(data_b)


test()
