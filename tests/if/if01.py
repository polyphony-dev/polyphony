from polyphony import testbench

def if01(x, y):
    if x == 0:
        z = y
        y *= 2
        y *= 3
        y *= 4
        y *= 5
        y *= 6
    else:
        z = y

    return y + z

@testbench
def test():
    assert 721 == if01(0, 1)
    assert 2 == if01(1, 1)
    assert 1442 == if01(0, 2)
test()
