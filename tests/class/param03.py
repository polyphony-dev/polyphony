from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

    def get_x(self):
        return self.x

def c_get_x_mul(c1, c2):
    return c1.get_x() * c2.get_x()

def param03(x):
    c1 = C(x)
    c2 = C(x+1)
    return c_get_x_mul(c1, c2)

@testbench
def test():
    assert 2 == param03(1)
    assert 6 == param03(2)
    assert 12 == param03(3)
