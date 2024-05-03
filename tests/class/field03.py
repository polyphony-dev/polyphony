from polyphony import testbench

class C:
    def __init__(self, x, y):
        self.x = x
        self.y = y

def field03(x, y):
    c = C(x, y)
    d = C(x+1, y+1)
    a = c.x + c.y + d.x + d.y
    c.x = 10
    return a + c.x

@testbench
def test():
    assert 18 == field03(1, 2)
    assert 22 == field03(2, 3)
    assert 26 == field03(3, 4)
