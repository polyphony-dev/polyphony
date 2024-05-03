from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

def alias01(x):
    c0 = C(x)
    c1 = c0
    c2 = c1
    result0 = c2.x == x and c1.x == x and c0.x == x
    c2.x = 10
    result1 = c2.x == 10 and c1.x == 10 and c0.x == 10
    return result0 and result1

@testbench
def test():
    assert alias01(1)
    assert alias01(2)
    assert alias01(3)
