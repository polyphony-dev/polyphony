from polyphony import testbench

def tuple02(x, y, z):
    ts = (x, y, z)*3
    s = 0
    for t in ts:
        s += t
    return s

@testbench
def test():
    assert 9 == tuple02(1, 1, 1)
    assert 18 == tuple02(1, 2, 3)
    assert 0 == tuple02(-1, 0, 1)

test()
