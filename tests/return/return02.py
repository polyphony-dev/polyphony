from polyphony import testbench

def return02(x, y, z):
    s = 1
    for i in range(x):
        if i == y + z:
            break
        s = s * 2
    return s

@testbench
def test():
    assert 1 == return02(0, 0, 0)
    assert 2 == return02(1, 1, 1)
    assert 32 == return02(10, 2, 3)

test()

