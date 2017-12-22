from polyphony import testbench


def list33(xs):
    s = 0
    for x in xs:
        s += x
    return s


@testbench
def test():
    lst2 = [3] * 4
    assert 3 * 4 == list33(lst2)

    lst1 = [6] * 4
    assert 6 * 4 == list33(lst1)


test()
