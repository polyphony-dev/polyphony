from polyphony import testbench


def f(v, i):
    if i == 0:
        return v
    elif i == 1:
        for k in range(i):
            v += 2
        return v
    else:
        for k in range(i):
            v += 1
        return v


def if27(code, r1, r2):
    if code == 0:
        return f(r1, r2)
    return 0


@testbench
def test():
    assert 3 == if27(0, 1, 1)
    assert 4 == if27(0, 2, 2)
    assert 6 == if27(0, 3, 3)
    assert 0 == if27(1, 4, 4)
