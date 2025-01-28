from polyphony import testbench


def list33(a):
    xs = [a] * 4
    s = 0
    for x in xs:
        s += x
    return s


@testbench
def test():
    assert 3 * 4 == list33(3)
    assert 6 * 4 == list33(6)
