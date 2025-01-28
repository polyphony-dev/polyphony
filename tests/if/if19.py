from polyphony import testbench


def if19(x):
    if x < 10:
        pass
    elif x < 20:
        return x + 1
    elif x < 30:
        assert False
    else:
        pass
    return x


@testbench
def test():
    assert 3 == if19(3)
    assert 14 == if19(13)
    assert 30 == if19(30)
