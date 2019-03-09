from polyphony import testbench


def f(v, i):
    if i == 0:
        return v
    elif i == 1:
        return v + 1
    else:
        for k in range(i):
            v += 1
        return v


def if26(code, r1, r2):
    if code == 0:
        return f(r1, r2)
    return 0


@testbench
def test():
    assert 2 == if26(0, 1, 1)
    assert 4 == if26(0, 2, 2)
    assert 6 == if26(0, 3, 3)
    assert 8 == if26(0, 4, 4)
    assert 0 == if26(1, 1, 1)


test()
