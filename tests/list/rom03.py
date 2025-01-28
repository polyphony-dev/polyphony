from polyphony import testbench

def rom03(x, y):
    data0 = [1, 2, 3]
    data1 = [4, 5, 6]
    data2 = [7, 8, 9]
    if x == 0:
        if y == 1:
            e = data0
        else:
            e = data1
        d = e
    elif x == 1:
        d = data1
    else:
        d = data2
    return d[0]

@testbench
def test():
    assert 1 == rom03(0, 1)
    assert 4 == rom03(1, 1)
    assert 7 == rom03(2, 1)
    assert 4 == rom03(0, 0)
