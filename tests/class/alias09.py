from polyphony import testbench

class C:
    def __init__(self, v):
        self.v = v

    def get_v(self):
        return self.v

def alias09(p, x, y):
    c0 = C(x)
    c1 = C(y)
    if p:
        c2 = c0
    else:
        c2 = c1
    c2.v += 10
    return c2.get_v()

@testbench
def test():
    assert 11 == alias09(True, 1, 2)
    assert 12 == alias09(True, 2, 3)
    assert 12 == alias09(False, 1, 2)
    assert 13 == alias09(False, 2, 3)

test()
