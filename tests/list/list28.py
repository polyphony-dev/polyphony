from polyphony import testbench


def list28(xs):
    xs[0] = 10
    x0 = xs[0]
    xs[0] = 100
    xs[1] = 11
    x00 = xs[0]
    x1 = xs[1]
    assert x0 == 10
    assert x00 == 100
    assert x1 == 11


@testbench
def test():
    list28([1, 2, 3])


test()
