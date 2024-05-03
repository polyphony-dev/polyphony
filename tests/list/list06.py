from polyphony import testbench

def list06(x):
    data = [1, 3, 5, x]
    data[0] = 1
    a = data[0]
    b = data[1]
    c = data[2]
    return a + b + c + x

@testbench
def test():
    assert 9 == list06(0)
    assert 10 == list06(1)
    assert 11 == list06(2)
