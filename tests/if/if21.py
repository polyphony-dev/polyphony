from polyphony import testbench


def if21(x):
    y = 0
    if x < 100:
        if x < 10:
            y = 10
        else:
            y = 20
        #y += 1
    else:
        if x < 200:
            y = 100
        else:
            y = 200
        y += 2
    return y


@testbench
def test():
    assert 10 == if21(0)
    assert 20 == if21(10)
    assert 20 == if21(20)
    assert 20 == if21(30)
    assert 102 == if21(100)
    assert 202 == if21(200)
