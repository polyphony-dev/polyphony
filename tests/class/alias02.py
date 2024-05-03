from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

class D:
    def __init__(self, c):
        self.c = c

def alias02(x):
    c0 = C(x)
    c1 = C(x*x)
    d = D(c0)
    result0 = d.c.x == x
    d.c = c1
    result1 = d.c.x == x*x
    c1.x = 0
    result2 = d.c.x == 0
    d.c = c0
    result3 = d.c.x == x

    return result0 and result1 and result2 and result3

@testbench
def test():
    assert alias02(1)
    assert alias02(2)
    assert alias02(3)
