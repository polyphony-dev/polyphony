from polyphony import testbench

class C:
    def __init__(self, v):
        self.v = v

    def get_v(self):
        return self.v

class D:
    def __init__(self, c):
        self.c = c

def alias06(p, x, y):
    c0 = C(x)
    c1 = C(y)
    if p:
        d = D(c0)
    else:
        d = D(c1)
    c0.v += 10
    return d.c.get_v()

@testbench
def test():
    assert 11 == alias06(True, 1, 2)
    assert 12 == alias06(True, 2, 3)
    assert 2 == alias06(False, 1, 2)
    assert 3 == alias06(False, 2, 3)
    
test()
