from polyphony import testbench

class C:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def get_x(self):
        return self.x

    def get_y(self):
        return self.y

def method01(x, y):
    c = C(x, y)
    return c.get_x() + c.get_y()

@testbench
def test():
    assert 3 == method01(1, 2)
    assert 5 == method01(2, 3)
    assert 7 == method01(3, 4)

test()
