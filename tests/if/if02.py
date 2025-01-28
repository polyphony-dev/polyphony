from polyphony import testbench

def if02(x, y, z):
    if x == 0:
        y *= 2
    elif y == 0:
        z *= 3
    elif z == 0:
        x *= 3
    else:
        z = y

    return y + z

@testbench
def test():
    assert 4 == if02(0, 1, 2)
    assert 3 == if02(2, 0, 1)
    assert 2 == if02(1, 2, 0)
