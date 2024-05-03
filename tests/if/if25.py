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


def if25():
    v = f(1, 0)
    return v


@testbench
def test():
    assert 1 == if25()
