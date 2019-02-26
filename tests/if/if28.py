from polyphony import testbench


def g(x):
    if x == 0:
        return 0
    return 1


def h(x):
    if x == 0:
        pass


def f(v, i, j, k):
    if i == 0:
        return v
    elif i == 1:
        return v
    elif i == 2:
        h(g(j) + g(k))
        return v
    elif i == 3:
        for m in range(j):
            v += 2
        return v
    else:
        for n in range(i):
            v += 1
        return v


def if28(code, r1, r2, r3, r4):
    if code == 0:
        return f(r1, r2, r3, r4)
    return 0


@testbench
def test():
    assert 1 == if28(0, 1, 1, 0, 0)
    assert 2 == if28(0, 2, 0, 0, 0)
    assert 3 == if28(0, 3, 1, 0, 0)
    assert 4 == if28(0, 4, 2, 0, 0)
    assert 5 == if28(0, 5, 2, 1, 1)
    assert 6 == if28(0, 6, 2, 2, 2)
    assert 7 == if28(0, 7, 3, 0, 0)
    assert 10 == if28(0, 8, 3, 1, 1)
    assert 13 == if28(0, 9, 3, 2, 2)
    assert 14 == if28(0, 10, 4, 0, 0)


test()
