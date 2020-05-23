from polyphony import testbench


def list34(xs):
    ys = [None] * len(xs)
    s = 0
    for i in range(len(xs)):
        ys[i] = xs[i] + 1
    for i in range(len(ys)):
        s += ys[i]
    return s


@testbench
def test():
    lst2 = [3] * 4
    assert 4 * 4 == list34(lst2)

    lst1 = [6] * 4
    assert 7 * 4 == list34(lst1)


test()
