from polyphony import testbench

class D:
    def __init__(self, x):
        self.x = x
        #self.y = y

class C:
    def __init__(self, x):
        self.d = D(x)

def composition01(x):
    c = C(x)
    a = c.d.x + c.d.x
    c.d.x = 10
    return a + c.d.x

@testbench
def test():
    assert 12 == composition01(1)
    assert 14 == composition01(2)
    assert 4 == composition01(-3)
