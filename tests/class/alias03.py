from polyphony import testbench

class C:
    def __init__(self, v):
        self.v = v

class D:
    def __init__(self, c):
        self.c = c

def alias03(p, x, y):
    c0 = C(x)
    c1 = C(y)
    d = D(c0)
    if p:
        d = D(c1)
    c0.v += 10
    return d.c.v

@testbench
def test():
    assert 2 == alias03(True, 1, 2)
    assert 3 == alias03(True, 2, 3)
    assert 11 == alias03(False, 1, 2)
    assert 12 == alias03(False, 2, 3)
    
test()
