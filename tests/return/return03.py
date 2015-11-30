from polyphony import testbench

def return03(x, y, z):
    s = 1
    for i in range(x):
        if i == y + z:
            return i
        s = s * 2
    return s

@testbench
def test():
    assert 1 == return03(0, 0, 0)
    assert 2 == return03(1, 1, 1)
    assert 5 == return03(10, 2, 3)

test()
