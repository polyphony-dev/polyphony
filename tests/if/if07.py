from polyphony import testbench

def if07(x, y):
    z = 0
    if False:
        z = x + y
    return z

@testbench
def test():
    assert 0 == if07(0, 0)
    assert 0 == if07(1, 1)
    assert 0 == if07(10, 10)
