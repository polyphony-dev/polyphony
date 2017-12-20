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
        print('!', v)
        return v
    elif i == 1:
        print('!!', v)
        return v
    elif i == 2:
        h(g(j) + g(k))
        print('!!!', v)
        return v
    elif i == 3:
        for m in range(j):
            v += 2
        print('!!!!', v)
        return v
    else:
        for n in range(i):
            v += 1
        print('!!!!!', v)
        return v


def cfg06(r0, r1, r2, r3, r4):
    if r0 == 0:
        return f(r1, r2, r3, r4)
    return 0


@testbench
def test():
    assert 0 == cfg06(1, 1, 1, 1, 1)
    assert 1 == cfg06(0, 1, 0, 1, 1)
    assert 2 == cfg06(0, 2, 1, 1, 1)
    assert 3 == cfg06(0, 3, 2, 1, 1)
    assert 7 == cfg06(0, 1, 3, 3, 4)
    assert 5 == cfg06(0, 1, 4, 3, 4)


test()
