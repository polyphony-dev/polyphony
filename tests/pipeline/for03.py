from polyphony import testbench
from polyphony import pipelined


def pipe_func(xs):
    s = 0
    for x in pipelined(xs):
        x = x + s
        s += x
    return s

def for03_a():
    xs = [1, 1, 1, 1, 1, 1, 1, 1]
    return pipe_func(xs)

def for03_b():
    xs = [1, 2, 3, 4, 5, 6, 7, 8]
    return pipe_func(xs)

@testbench
def test():
    assert 255 == for03_a()
    assert 502 == for03_b()
