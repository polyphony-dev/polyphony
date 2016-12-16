from polyphony import testbench

def tuple08(p, x, y):
    if p:
        ts = (x,)*4
    else:
        ts = (y,)*4
    a, b, c, d = ts
    return a+b+c+d

@testbench
def test():
    assert 4 == tuple08(True, 1, 2)
    assert 12 == tuple08(False, 2, 3)

test()
