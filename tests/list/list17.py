from polyphony import testbench


def list17(x):
    data0 = [1, 2, 3]
    data1 = [4, 5, 6]
    d = data0
    d = data1
    if x == 0:
        d = data0
    elif x == 1:
        d = data1
    elif x == 2:
        d = data0
    else:
        d = data1
    return d[0]


@testbench
def test():
    assert 1 == list17(0)
    assert 4 == list17(1)
    assert 1 == list17(2)
    assert 4 == list17(3)


test()
