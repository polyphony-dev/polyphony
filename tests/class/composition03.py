from polyphony import testbench

class E:
    def __init__(self, x):
        self.x = x

class D:
    def __init__(self, x):
        self.e = E(x)

class C:
    def __init__(self, x):
        self.d = D(x)

def composition03(x):
    c = C(x)
    a = c.d.e.x + c.d.e.x
    c.d.e.x = 10
    return a + c.d.e.x

@testbench
def test():
    assert 12 == composition03(1)
    assert 14 == composition03(2)
    assert 4  == composition03(-3)

test()
