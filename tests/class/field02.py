from polyphony import testbench

class C:
    def __init__(self, x, y):
        self.x = x
        self.y = y

def field02(x, y):
    c = C(x, y)
    a = c.x + c.y
    c.x = 10
    return a + c.x

@testbench
def test():
    assert 13 == field02(1, 2)
    assert 15 == field02(2, 3)
    assert 17 == field02(3, 4)
