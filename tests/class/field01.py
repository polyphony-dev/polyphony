from polyphony import testbench

class C:
    def __init__(self, x, y):
        self.x = x
        self.y = y

def field01(x, y):
    c = C(x, y)
    return c.x + c.y

@testbench
def test():
    assert 3 == field01(1, 2)
    assert 5 == field01(2, 3)
    assert 7 == field01(3, 4)

test()
