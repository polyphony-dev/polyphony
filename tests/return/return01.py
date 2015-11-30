from polyphony import testbench

def return01(x, y, z):
    if z == 1:
        x = x + y
        return x + y
    elif z == 2:
        x = x - y
        return x - y
    return x

@testbench
def test():
    assert 0 == return01(0, 0, 0)
    assert 3 == return01(1, 1, 1)
    assert -2 == return01(2, 2, 2)

test()
