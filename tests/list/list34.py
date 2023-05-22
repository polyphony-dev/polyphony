from polyphony import testbench


def list34(x):
    xs = [x] * 4
    ys = [None] * len(xs)
    s = 0
    for i in range(len(xs)):
        ys[i] = xs[i] + 1
    for i in range(len(ys)):
        s += ys[i]
    return s


@testbench
def test():
    assert 4 * 4 == list34(3)
    assert 7 * 4 == list34(6)


test()
