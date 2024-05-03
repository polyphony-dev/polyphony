from polyphony import testbench

def list02(x, y):
    a = [x, 2, 3]*3
    b = a
    for i in range(3):
        b[i] = a[i] * 2
    return a[x] + b[y]

@testbench
def test():
    assert 6 == list02(1, 0)
    assert 12 == list02(2, 2)
    assert 5 == list02(3, 4)
