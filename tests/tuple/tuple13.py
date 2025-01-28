from polyphony import testbench


def tuple13():
    t = (0, 1, 2)
    a, b, c = t
    return a + b + c


@testbench
def test():
    assert 3 == tuple13()
