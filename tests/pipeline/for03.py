from polyphony import testbench
from polyphony import pipelined


def pipe_func(xs):
    s = 0
    for x in pipelined(xs):
        x = x + s
        s += x
    return s

def pipe03_a():
    xs = [1, 1, 1, 1, 1, 1, 1, 1]
    return pipe_func(xs)

def pipe03_b():
    xs = [1, 2, 3, 4, 5, 6, 7, 8]
    return pipe_func(xs)

@testbench
def test():
    assert 255 == pipe03_a()
    assert 502 == pipe03_b()


test()
