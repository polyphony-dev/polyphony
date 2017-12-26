from polyphony import testbench


def f(v, i):
    if i == 0:
        return v
    else:
        v += 1
        if i == 1:
            return v + v
        else:
            for k in range(8):
                v += 1
            return v


def cfg03(a, b):
    v = f(1, 0)
    return v + f(a, b)


@testbench
def test():
    assert 12 == cfg03(2, 2)


test()