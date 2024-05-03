from polyphony import testbench

def tuple04(x, y):
    t = x, y
    y, x = t
    return x


@testbench
def test():
    assert 2 == tuple04(1, 2)
    assert 3 == tuple04(2, 3)
