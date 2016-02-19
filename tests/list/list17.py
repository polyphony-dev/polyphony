from polyphony import testbench

def list17(x, y, z):
    data0 = [1, 2, 3]
    data1 = [4, 5, 6]
    d = data0
    d = data1
    if x:
        d = data0
    else:
        d = data1
    return d[0]

@testbench
def test():
    assert 4 == list17(0, 1, 4)
    assert 1 == list17(1, 1, 4)
    assert 1 == list17(2, 1, 4)
test()
