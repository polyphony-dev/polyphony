from polyphony import testbench

class C:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def get_x(self):
        return self.x

    def get_y(self):
        return self.y

    def set_x(self, x):
        self.x = x

    def set_y(self, y):
        self.y = y

def method03(x, y):
    c = C(x, y)
    a = c.get_x() + c.get_y()
    c.set_x(x*2)
    c.set_y(y*2)
    b = c.x + c.y
    return a + b

@testbench
def test():
    assert 9  == method03(1, 2)
    assert 15 == method03(2, 3)
    assert 21 == method03(3, 4)
