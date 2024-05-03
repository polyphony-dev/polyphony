from polyphony import testbench


def f(p0, p1, p2):
    if p0 == 0:
        if p1 == 0:
            if p2 == 0:
                return 1
            elif p2 == 1:
                return 2
            else:
                return 3
        elif p1 == 1:
            if p2 == 0:
                return 4
            else:
                return 5
        elif p1 == 2:
            if p2 == 0:
                return 6
            else:
                return 7
        else:
            return 8
    elif p0 == 1:
        if p1 == 0:
            if p2 == 0:
                return 9
            elif p2 == 1:
                return 10
            else:
                return 11
        elif p1 == 1:
            if p2 == 0:
                return 12
            else:
                return 13
        elif p1 == 2:
            if p2 == 0:
                return 14
            else:
                return 15
        else:
            return 16


def if30(p0, p1, p2):
    a = f(p0, p1, p2)
    b = f(p0, p1, p2)
    return a if p0 else b


@testbench
def test():
    assert 1 == if30(0, 0, 0)
    assert 2 == if30(0, 0, 1)
    assert 3 == if30(0, 0, 2)
    assert 4 == if30(0, 1, 0)
    assert 5 == if30(0, 1, 1)
    assert 6 == if30(0, 2, 0)
    assert 7 == if30(0, 2, 1)
    assert 8 == if30(0, 3, 0)
    assert 9 == if30(1, 0, 0)
    assert 10 == if30(1, 0, 1)
    assert 11 == if30(1, 0, 2)
    assert 12 == if30(1, 1, 0)
    assert 13 == if30(1, 1, 1)
    assert 14 == if30(1, 2, 0)
    assert 15 == if30(1, 2, 1)
    assert 16 == if30(1, 3, 0)
