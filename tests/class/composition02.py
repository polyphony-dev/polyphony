from polyphony import testbench

class D:
    def __init__(self, x):
        self.x = x

class C:
    def __init__(self, x, y):
        self.d1 = D(x)
        self.d2 = D(y)

def composition02(x, y):
    c = C(x, y)
    a = c.d1.x + c.d2.x
    c.d1.x = 10
    return a + c.d1.x

@testbench
def test():
    assert 13 == composition02(1, 2)
    assert 16 == composition02(2, 4)
    assert 10 == composition02(-3, 3)

test()
