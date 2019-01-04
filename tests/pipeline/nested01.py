from polyphony import testbench
from polyphony import pipelined


def nested01(xs, ys, w, h):
    for y in pipelined(range(h)):
        for x in range(w):
            idx = y * w + x
            v = xs[idx]
            ys[idx] = v + 1


@testbench
def test():
    width = 16
    height = 16
    data0 = [0] * width * height
    data1 = [0] * width * height
    for i in range(width * height):
        data0[i] = i
    nested01(data0, data1, width, height)
    for i in range(width * height):
        assert data1[i] == i + 1


test()
