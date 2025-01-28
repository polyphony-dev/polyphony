from polyphony import testbench


def if20(x):
    y = 0
    if x < 100:
        if x < 10:
            y += 1
        elif x < 20:
            y += 2
        elif x < 30:
            y += 3
        else:
            pass
        y += 20
    else:
        y = 100
    return y


@testbench
def test():
    assert 21 == if20(0)
    assert 22 == if20(10)
    assert 23 == if20(20)
    assert 20 == if20(30)
    assert 100 == if20(100)
