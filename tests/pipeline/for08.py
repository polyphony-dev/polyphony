from polyphony import testbench
from polyphony import pipelined


def pipe_func(xs, ys):
    s = 0
    for i in pipelined(range(len(xs))):
        idx = i + s
        if idx > 4:
            idx = 0
        v = xs[idx]
        ys[i] = v
        s = s + v


def pipe08():
    data = [0, 16, 32, -16, -64]
    out = [0] * 5
    pipe_func(data, out)
    #print(out)
    assert 0 == out[0]
    assert 16 == out[1]
    assert 0 == out[2]
    assert 0 == out[3]
    assert 0 == out[4]


@testbench
def test():
    pipe08()

test()
