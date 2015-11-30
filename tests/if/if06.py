from polyphony import testbench

def if06(x, y):
    z = 0
    if True:
        z = x + y
    return z

@testbench
def test():
    assert 0 == if06(0, 0)
    assert 2 == if06(1, 1)
    assert 20 == if06(10, 10)
test()
