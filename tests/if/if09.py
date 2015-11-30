from polyphony import testbench

def if09(x, y):
    z = 0
    c = [0]
    if c[0]:
        z = x + y
    return z

@testbench
def test():
    assert 0 == if09(0, 0)
    assert 0 == if09(1, 1)
    assert 0 == if09(10, 10)
test()
