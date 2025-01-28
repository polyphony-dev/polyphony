from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

    def get_x(self):
        return self.x

    def set_x(self, x):
        self.x = x

def method02(x):
    c = C(x)
    a = c.get_x() + c.get_x()
    c.set_x(x*2)
    b = c.x + c.x
    return a + b

@testbench
def test():
    assert 6  == method02(1)
    assert 12 == method02(2)
    assert 18 == method02(3)
