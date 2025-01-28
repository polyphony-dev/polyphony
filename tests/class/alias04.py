from polyphony import testbench

class C:
    def __init__(self, v):
        self.v = v

class D:
    def __init__(self, c):
        self.c = c

class E:
    def __init__(self, d):
        self.d = d

def alias04(p, x, y):
    c1 = C(x)
    c2 = C(y)
    d1 = D(c1)
    d2 = D(c2)
    if p:
        e = E(d1)
    else:
        e = E(d2)
    return e.d.c.v

@testbench
def test():
    assert 1 == alias04(True, 1, 2)
    assert 2 == alias04(True, 2, 3)
    assert 2 == alias04(False, 1, 2)
    assert 3 == alias04(False, 2, 3)
