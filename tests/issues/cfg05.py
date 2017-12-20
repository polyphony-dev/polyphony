from polyphony import testbench


def f(v, i):
    if i == 0:
        print('!', v)
        return v
    elif i == 1:
        for k in range(i):
            v += 2
        print('!!', v)
        return v
    else:
        for k in range(i):
            v += 1
        print('!!!', v)
        return v


def cfg05(r0, r1, r2):
    if r0 == 0:
        return f(r1, r2)
    return 0


@testbench
def test():
    assert 0 == cfg05(1, 1, 1)
    assert 2 == cfg05(0, 2, 0)
    assert 3 == cfg05(0, 1, 1)
    assert 4 == cfg05(0, 0, 4)


test()
