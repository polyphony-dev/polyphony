from polyphony import testbench
from polyphony import pipelined


def nested01_func(xs, ys, w, h):
    for y in pipelined(range(h)):
        for x in range(w):
            idx = y * w + x
            v = xs[idx]
            ys[idx] = v + 1


def nested01():
    width = 16
    height = 16
    data0 = [0] * width * height
    data1 = [0] * width * height
    for i in range(width * height):
        data0[i] = i
    nested01_func(data0, data1, width, height)
    for i in range(width * height):
        assert data1[i] == i + 1


@testbench
def test():
    nested01()


test()
