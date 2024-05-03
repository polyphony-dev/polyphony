from polyphony import testbench

def if08(x, y):
    z = 0
    c = [1]
    if c[0]:
        z = x + y
    return z

@testbench
def test():
    assert 0 == if08(0, 0)
    assert 2 == if08(1, 1)
    assert 20 == if08(10, 10)
