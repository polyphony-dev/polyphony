from polyphony import testbench

def tuple05(p, x, y):
    if p:
        ts = (x,)*4
    else:
        ts = (y,)*4
    s = 0
    for t in ts:
        s += t
    return s


@testbench
def test():
    assert 4 == tuple05(True, 1, 2)
    assert 12 == tuple05(False, 2, 3)
