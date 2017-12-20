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


def cfg02(x):
    return f(x)


@testbench
def test():
    assert 1 == cfg02(0)
    assert 2 == cfg02(1)
    assert 3 == cfg02(2)


test()

