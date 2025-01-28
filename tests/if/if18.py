from polyphony import testbench


def if18(x):
    if x < 10:
        pass
    elif x < 20:
        x = -x
    elif x < 30:
        pass
    else:
        x = x * x

    return x


@testbench
def test():
    assert 0 == if18(0)
    assert -10 == if18(10)
    assert 20 == if18(20)
    assert 900 == if18(30)
