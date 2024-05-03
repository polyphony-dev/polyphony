from polyphony import testbench

def tuple03(x, y):
    y, x = x, y
    return x

@testbench
def test():
    assert 2 == tuple03(1, 2)
    assert 3 == tuple03(2, 3)
