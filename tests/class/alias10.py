from polyphony import testbench

class C:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


def alias10(p, a, b, c):
    c0 = C(a, b, c)
    c1 = C(b, c, a)
    c2 = C(c, a, b)
    d = c0
    if p == 0:
        d = c0
    elif p == 1:
        d = c1
    elif p == 2:
        d = c2
    d.x += d.y * 2 + d.z * 3
    return d.x + d.y


@testbench
def test():
    assert 16 == alias10(0, 1, 2, 3)
    assert 21 == alias10(1, 2, 3, 4)
    assert 26 == alias10(2, 3, 4, 5)
    assert 37 == alias10(3, 4, 5, 6)

test()
