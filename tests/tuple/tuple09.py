from polyphony import testbench


def first(t):
    x, y, z = t
    return x


def second(t):
    x, y, z = t
    return y


def tuple09(x, y, z):
    t = (x, y, z)
    return first(t) + second(t)


@testbench
def test():
    assert 1 + 2 == tuple09(1, 2, 3)
    assert 4 + 5 == tuple09(4, 5, 6)


test()
