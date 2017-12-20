from polyphony import testbench


def f(v, i):
    if i == 0:
        print('!', v)
        return v
    elif i == 1:
        v += 1
        print('!!', v)
        return v
    else:
        for k in range(i):
            v += 1
        print('!!!', v)
        return v


def cfg04(r0, r1):
    return f(r0, r1)


@testbench
def test():
    assert 1 == cfg04(1, 0)
    assert 2 == cfg04(1, 1)
    assert 3 == cfg04(1, 2)


test()
