from polyphony import testbench

class C:
    def __init__(self, v):
        self.v = v

    def get_v(self):
        return self.v

class D:
    def get_c(self, c):
        return c

def alias07(p, x, y):
    c0 = C(x)
    c1 = C(y)
    if p:
        c = D().get_c(c0)
    else:
        c = D().get_c(c1)
    c0.v += 10
    return c.get_v()

@testbench
def test():
    assert 11 == alias07(True, 1, 2)
    assert 12 == alias07(True, 2, 3)
    assert 2 == alias07(False, 1, 2)
    assert 3 == alias07(False, 2, 3)

test()
