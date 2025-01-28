from polyphony import testbench

def list24(x):
    data0 = [x]
    data1 = [x, x]
    data2 = [x, x, x]
    data3 = [x, x, x, x]
    if x == 0:
        d = data0
    elif x == 1:
        d = data1
    elif x == 2:
        d = data2
    else:
        d = data3
    return len(d)

@testbench
def test():
    assert 1 == list24(0)
    assert 2 == list24(1)
    assert 3 == list24(2)
    assert 4 == list24(3)
