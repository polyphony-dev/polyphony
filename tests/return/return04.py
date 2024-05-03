from polyphony import testbench

def return04(x, y, z):
    s = 1
    for i in range(x):
        for j in range(y):
            if i == j == z:
                return i
        s = s * 2
    return s

@testbench
def test():
    assert 1 == return04(0, 0, 0)
    assert 2 == return04(1, 1, 1)
    assert 1024 == return04(10, 2, 3)
