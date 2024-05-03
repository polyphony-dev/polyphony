from polyphony import testbench


def f(p):
    if p == 0:
        return 1
    else:
        if p == 1:
            return 2
        elif p == 2:
            return 3
    return 0


def if24(x):
    return f(x)


@testbench
def test():
    assert 1 == if24(0)
    assert 2 == if24(1)
    assert 3 == if24(2)
